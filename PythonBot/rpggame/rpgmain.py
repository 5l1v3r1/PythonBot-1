import datetime
import logging
import os
import os.path
import random
from io import BytesIO

import discord
import math
import requests
from PIL import Image, ImageFont, ImageDraw
from discord.ext import commands

import constants
from rpggame import rpgcharacter as rpgchar, rpgdbconnect as dbcon, rpggameactivities, rpgconstants as rpgc
from rpggame.rpgcharacter import RPGCharacter
from rpggame.rpgmonster import RPGMonster
from rpggame.rpgpet import RPGPet
from rpggame.rpgplayer import RPGPlayer
from secret.secrets import font_path

RPG_EMBED_COLOR = 0x710075
STANDARD_BATTLE_TURNS = 50
BATTLE_TURNS = {"Bossbattle": 200}


class RPGGame:
    def __init__(self, my_bot):
        self.bot = my_bot
        self.logger = logging.getLogger(__name__)
        self.boss_parties = {}
        self.players = {}
        self.top_lists = {}
        self.game_init()
        print('RPGGame started')

    async def check_role(self, role: str, message: discord.Message) -> bool:
        if role not in [x[0] for x in rpgc.names.get("role")]:
            await self.bot.say("You are still Undead. "
                               "Please select a class with '{}rpg role' in order to start to play!".format(
                self.bot._get_prefix(message)))
            return False
        return True

    @staticmethod
    def add_health_rep(players: [RPGCharacter]):
        health_report = ""
        for m in players:
            health_report += m.name + " ({})\n".format(m.health)
        if len(health_report) > 0:
            return health_report
        return None

    @staticmethod
    def construct_battle_report(title_length: int, report_actions: [(RPGCharacter, RPGCharacter, int, bool)]) -> (
            list, str):
        battle = []
        text = ''

        for attacker in set([s[0] for s in report_actions]):
            attackers_attacks = [s for s in report_actions if s[0] == attacker]
            for defender in set([x[1] for x in attackers_attacks]):
                hits = [(s[2], s[3]) for s in attackers_attacks if s[1] == defender]
                text += '\n**{}** attacked **{}** {} times for a total of {} damage'.format(attacker.name,
                                                                                            defender.name, len(hits),
                                                                                            sum([x[0] for x in hits]))
                crits = sum([1 for x in hits if x[1]])
                if crits == 1:
                    text += ', including a critical!'
                if crits > 1:
                    text += ', including {} criticals!'.format(crits)

                # Split up message because of discords character limit
                if len(text) > (900 if len(battle) > 0 else 900 - title_length):
                    battle.append(text)
                    text = ''

        # Min and max damage
        if len(report_actions) > 0:
            max_char, _, max_dam, _ = max(report_actions, key=lambda item: item[2])
            stats = '**{}** did the most damage ({})'.format(max_char.name, max_dam)
            min_char, _, min_dam, _ = min(report_actions, key=lambda item: item[2])
            if min_dam != max_dam:
                stats += '\n**{}** did the least damage ({})'.format(min_char.name, min_dam)

        battle.append(text)
        return battle, stats

    async def resolve_battle(self, battle_name: str, channel: discord.Channel, p1: [RPGCharacter],
                             p2: [RPGMonster], thumbnail=None):

        # Gather report header information
        embed = discord.Embed(colour=RPG_EMBED_COLOR)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        title = ""
        if len(p1) == 1:
            title += "{} ({}hp, {})".format(p1[0].name, p1[0].health, rpgc.elementnames.get(p1[0].get_element())[0])
        else:
            title += "A party of {}".format(len(p1))
        title += " vs "
        if len(p2) == 1:
            title += "{} ({}hp, {})".format(p2[0].name, p2[0].health, rpgc.elementnames.get(p2[0].get_element())[0])
        else:
            title += "A party of {}".format(len(p2))
        embed.add_field(name=battle_name, value=title, inline=False)
        battle_report = []
        i = 0

        # Save healthvalues in case of mockbattle
        h1 = []
        h2 = []
        for i in range(len(p1)):
            h1.append(p1[i].health)
        for i in range(len(p2)):
            h2.append(p2[i].health)

        # Fight starts
        # Fight stops when either party (not including pets) runs out of health
        turns = BATTLE_TURNS.get(battle_name, STANDARD_BATTLE_TURNS)
        while (i < turns) and (sum([x.health for x in p1]) > 0) and (sum([x.health for x in p2]) > 0):
            attackers = list(p1)

            # Pets are added to allow them to attack
            for p in [x for x in p1 if isinstance(x, RPGPlayer) and x.health > 0]:
                attackers += p.pets
            for attacker in attackers:
                if attacker.health > 0:

                    # Choose attackers target
                    defs = [x for x in p2 if x.health > 0]
                    if len(defs) <= 0:
                        break
                    defender = random.choice(defs)
                    ws = random.randint(0, attacker.get_weaponskill() + defender.get_weaponskill())

                    # Determine whether the attacker hits and for how much damage
                    if ws < attacker.get_weaponskill():
                        if ws < min(int(attacker.get_weaponskill() / 3), attacker.get_critical()):
                            damage = int((2 + (math.log(
                                max(0, attacker.get_critical() - int(attacker.get_weaponskill() / 3)) + 1)) / pow(
                                2 * attacker.get_level(), 0.3)) * attacker.get_damage(defender.get_element()))
                            battle_report.append((attacker, defender, damage, True,))

                        else:
                            damage = int(math.floor(
                                math.sqrt(random.randint(100, 400) / 100) * attacker.get_damage(
                                    defender.get_element())))
                            battle_report.append((attacker, defender, damage, False,))

                        defender.add_health(-1 * damage, death=not (battle_name == "Mockbattle"))

            # Switch attackers and defenders roles
            p3 = p1
            p1 = p2
            p2 = p3
            i += 1

        # Convert battle actions to text report
        battle_report_text, battle_report_stats = self.construct_battle_report(len(title), battle_report)

        # Calculate result of the battle
        if sum([x.health for x in p1]) <= 0:
            if (len(p1) == 1) and (len(p2) == 1):
                result = "{} ({}) laughs while walking away from {}'s corpse".format(p2[0].name, p2[0].health,
                                                                                     p1[0].name)
                healthrep = None
            else:
                result = "{}'s party completely slaughtered {}'s party".format(p2[0].name, p1[0].name)
                healthrep = self.add_health_rep(p1 + p2)
        else:
            result = "The battle lasted long, both parties are exhausted.\nThey agree on a draw this time"
            healthrep = self.add_health_rep(p1 + p2)

        # Assemble embeds and send battle report to discord channel
        for i in range(len(battle_report_text) - 1):
            embed.add_field(name="Battle report", value=battle_report_text[i], inline=False)
            await self.bot.send_message(channel, embed=embed)
            embed = discord.Embed(colour=RPG_EMBED_COLOR)

        text_length = len(battle_report_text[-1])
        embed.add_field(name="Battle report", value=battle_report_text[-1], inline=False)

        if text_length > 900:
            await self.bot.send_message(channel, embed=embed)
            embed = discord.Embed(colour=RPG_EMBED_COLOR)
            text_length = 0

        embed.add_field(name='Stats', value=battle_report_stats)
        text_length += len(battle_report_stats)

        if text_length > 900:
            await self.bot.send_message(channel, embed=embed)
            embed = discord.Embed(colour=RPG_EMBED_COLOR)
            text_length = 0

        if healthrep:
            embed.add_field(name="Health report", value=healthrep)
            text_length += len(healthrep)
            if text_length > 900:
                await self.bot.send_message(channel, embed=embed)
                embed = discord.Embed(colour=RPG_EMBED_COLOR)

        embed.add_field(name="Result", value=result)
        try:
            await self.bot.send_message(channel, embed=embed)
        except discord.HTTPException:
            try:
                await self.bot.send_message(channel, '\n'.join(battle_report_text + [result]))
            except discord.HTTPException as e:
                self.bot.pretty_error_str(e)

        # Switch teams to original positions
        if i % 2 == 1:
            p3 = p1
            p1 = p2
            p2 = p3

        # Restore health to saved values
        if battle_name == "Mockbattle":
            for i in range(len(p1)):
                p1[i].health = h1[i]
            for i in range(len(p2)):
                p2[i].health = h2[i]

        # Return who won
        # Winning means having dealt a higher percentage of damage
        if sum([(x.health / x.get_max_health()) for x in p1]) > sum([(x.health / x.get_max_health()) for x in p2]):
            return 1
        return 2

    async def boss_battle(self):
        print("Boss time!")
        try:
            for serverid in self.boss_parties:
                party = self.boss_parties.get(serverid)
                if len(party) > 0:
                    channel = self.bot.get_channel(dbcon.get_rpg_channel(str(serverid)))
                    if not channel:
                        print("No channel for {}".format(serverid))
                        return

                    # Determine bossbattle difficulty
                    lvl = max([x.get_bosstier() for x in party])
                    bosses = []
                    while (3 * len(bosses)) < len(party):
                        (name, elem, pic) = random.choice(rpgc.bosses)
                        bosses.append(RPGMonster(name=name, health=int(52 * lvl * lvl), damage=int(lvl * lvl * 1.1),
                                                 ws=int(lvl * lvl * 0.6), element=elem))

                    winner = await self.resolve_battle("Bossbattle", channel, party, bosses, thumbnail=pic)

                    if winner == 1:
                        # Reward the winners with exp, money and a bosstier
                        for p in party:
                            reward = 32 * lvl * lvl * len(bosses) / len(party)
                            p.add_exp(reward)
                            p.add_bosstier()
                            for pet in p.pets:
                                pet.add_exp(0.13 * reward if p.role == rpgc.names.get('role')[2][0] else 0.1 * reward)

                        # Chance to reward a player with a new pet
                        if random.randint(0, 100) < 35:
                            petwinner = random.choice(party)
                            petname = 'Pet ' + bosses[0].name
                            pet = RPGPet(name=petname, damage=petwinner.get_bosstier() * 10,
                                         weaponskill=petwinner.get_bosstier())
                            if pet and petwinner.add_pet(pet):
                                await self.bot.send_message(channel,
                                                            '{} found a baby {}, a new pet!'.format(petwinner.name,
                                                                                                    petname))
        except Exception as e:
            print(self.bot.pretty_error_str(e))
        # Reset players busy status and clear past bossraid info
        for p in self.players.values():
            if p.busydescription == rpgchar.BUSY_DESC_BOSSRAID:
                p.reset_busy()
        self.boss_parties = {}

    async def adventure_encounter(self, player: RPGPlayer, channel: discord.Channel):
        # Choose monster and determine battle difficulty
        (name, elem, pic) = random.choice(rpgc.monsters)
        lvl = player.get_level()
        winner = await self.resolve_battle("Adventure encounter", channel, [player], [
            RPGMonster(name=name, health=(int(10 + math.floor(player.exp / 75))),
                       damage=int(math.floor(7 * lvl)), ws=int(math.floor(1 + (0.085 * (player.exp ** 0.62)))),
                       element=elem)], thumbnail=pic)

        # Reward victory
        if winner == 1:
            lvl = math.pow(player.get_level(), 0.9)
            player.add_exp(int(110 * lvl))
            player.add_money(int(25 * lvl))
            for p in player.pets:
                p.add_exp(13 * lvl if player.role == rpgc.names.get('role')[2][0] else 10 * lvl)

    async def adventure_secret(self, player: RPGPlayer, channel: discord.Channel):
        secrets_list = rpgc.adventureSecrets
        (name, stat, amount) = secrets_list[random.randint(0, len(secrets_list) - 1)]

        if stat.lower() == "health":
            player.add_health(amount)
            amount *= max(1, int(player.get_level() / 4))
        elif stat.lower() == "weaponskill":
            amount *= max(1, int(math.pow(player.get_level(), 0.25)))
            player.weaponskill += amount
        elif stat.lower() == "money":
            amount *= max(1, int(math.sqrt(player.get_level())))
            player.money += amount
        elif stat.lower() == "exp":
            amount *= max(1, int(math.sqrt(player.get_level() / 2)))
            player.exp += amount
        elif stat.lower() == "damage":
            amount *= max(1, int(math.pow(player.get_level(), 0.4)))
            player.damage += amount
        embed = discord.Embed(colour=RPG_EMBED_COLOR)
        embed.add_field(name="Adventure secret found", value="{}, {}\n{} +{}".format(player.name, name, stat, amount))
        await self.bot.send_message(channel, embed=embed)

    def get_boss_parties(self):
        parties = {}
        for p in self.players.values():
            if p.busydescription == rpgchar.BUSY_DESC_BOSSRAID:
                party = parties.get(p.busychannel)
                if party is None:
                    party = []
                    self.boss_parties[p.busychannel] = party
                party.append(p)
        return parties

    def game_init(self):
        self.players = dbcon.get_busy_players(self.bot)
        self.boss_parties = self.get_boss_parties()
        logging.basicConfig(level=logging.DEBUG)
        print("RPGGame loop started!")

    async def game_tick(self, time):
        try:
            if time.minute % 5 == 0:
                print(time)

            if time.minute == 55:
                # Boss raids
                for p in [x for x in self.boss_parties if len(x) > 0]:
                    channel = self.bot.get_channel(dbcon.get_rpg_channel(str(p)))
                    if not channel:
                        print("No channel for {}".format(p))
                        return
                    await self.bot.send_message(channel, "A party of {} is going to fight the boss in 5 minutes!!\n"
                                                         "Join fast if you want to participate".format(
                        len(self.boss_parties.get(p))))

            if time.minute == 0:
                await self.boss_battle()
                self.bot.rpgshop.weapons = {}
                self.bot.rpgshop.armors = {}

            # Saving stats to db
            if time.minute % 15 == 0:
                p = self.players.values()
                if len(p) > 0:
                    dbcon.update_players(p)
                    player_ids = list(self.players.keys())
                    for i in player_ids:
                        player = self.players.get(i)
                        if (player.busydescription == rpgchar.BUSY_DESC_NONE) and (
                                player.health >= player.get_max_health()):
                            self.players.pop(i)
                    print("Players saved")
        except Exception as e:
            print(e)
            self.logger.exception(e)

        # Player is doing rpg stuff
        for u in list(self.players.values()):
            try:
                if u.busydescription is not rpgchar.BUSY_DESC_NONE:
                    if not (u.busydescription in [rpgchar.BUSY_DESC_BOSSRAID]):
                        u.busytime -= 1
                    c = self.bot.get_channel(str(u.busychannel))
                    try:
                        if not c:
                            c = await self.bot.get_user_info(str(u.busychannel))
                        if u.busydescription == rpgchar.BUSY_DESC_ADVENTURE and random.randint(0, 4) <= 0:
                            await self.adventure_encounter(u, c)
                        elif (u.busydescription in [rpgchar.BUSY_DESC_ADVENTURE, rpgchar.BUSY_DESC_WANDERING]) and (
                                random.randint(0, 14) <= 0):
                            await self.adventure_secret(u, c)
                        if u.busytime <= 0:
                            embed = discord.Embed(colour=RPG_EMBED_COLOR)
                            if u.busydescription == rpgchar.BUSY_DESC_ADVENTURE:
                                action_type = "adventure"
                                action_name = "adventuring"
                            elif u.busydescription == rpgchar.BUSY_DESC_TRAINING:
                                action_type = action_name = "training"
                            elif u.busydescription == rpgchar.BUSY_DESC_WANDERING:
                                action_type = action_name = "wandering"
                            elif u.busydescription == rpgchar.BUSY_DESC_WORKING:
                                action_type = "work"
                                action_name = "working"
                            else:
                                action_type = action_name = "Unknown"
                            if u.health > 0:
                                embed.add_field(name="Ended {}".format(action_type),
                                                value="You are now done {}".format(action_name))
                            else:
                                embed.add_field(name="You Died".format(action_type),
                                                value="You were killed on one of your adventures".format(action_name))
                                embed.set_thumbnail(url="https://res.cloudinary.com/teepublic/image/private/s--_1_FlGA"
                                                        "a--/t_Preview/b_rgb:191919,c_limit,f_jpg,h_630,q_90,w_630/v146"
                                                        "6191557/production/designs/549487_1.jpg")
                            c = await self.bot.get_user_info(str(u.userid))
                            if c:
                                try:
                                    await self.bot.send_message(c, embed=embed)
                                except discord.errors.Forbidden:
                                    pass
                            else:
                                print("Channel not found, {} is done with {}".format(u.name, u.busydesription))
                            u.reset_busy()
                    except discord.errors.NotFound:
                        u.reset_busy()
                if u.health < u.get_max_health():
                    u.do_auto_health_regen()
            except Exception as e:
                print(e)
                self.logger.exception(e)

    def get_party(self, serverid):
        party = self.boss_parties.get(serverid)
        if not party:
            party = []
            self.boss_parties[serverid] = party
        return party

    def get_player_data(self, userid: str, name=None) -> RPGPlayer:
        p = self.players.get(userid)
        if not p:
            p = dbcon.get_single_player(self.bot, userid)
            self.players[userid] = p
        if name:
            p.name = name
        return p

    async def handle(self, message: discord.Message):
        data = self.get_player_data(message.author.id, name=message.author.display_name)
        if data.role not in [x[0] for x in rpgc.names.get("role")]:
            return
        # Reward player based on rpg level with money
        i = round(pow((data.get_level()) + 1, 1 / 2)  # levelbonus
                  * max(0, min(80, int((len(message.content) - 3) / 1.5))))  # Textbonus
        if data.busydescription in [rpgchar.BUSY_DESC_TRAINING, rpgchar.BUSY_DESC_BOSSRAID]:
            i *= 0.5
        data.add_money(int(i))
        data.add_exp(1)

    def quit(self):
        # Save rpg stats
        dbcon.update_players(self.players.values())
        print("RPGStats saved")

    async def send_help_message(self, ctx):
        prefix = self.bot._get_prefix(ctx.message)
        await self.bot.say(
            "Your '{}rpg' has been heard, you will be send the commands list for the rpg game".format(
                prefix))

        # Intro/setup help
        embed = discord.Embed(colour=RPG_EMBED_COLOR)
        embed.set_author(name="RPG Help: Basics", icon_url=self.bot.user.avatar_url)
        embed.add_field(name="Introduction", value="Welcome adventurer, this game grants you the opportunity to slay "
                                                   "monsters and rule a realm. You can train yourself and buy upgrades "
                                                   "at the shop, and when you are done with adventuring, you can even "
                                                   "challenge a boss every hour with a group of friends.",
                        inline=False)
        embed.add_field(name="Basics",
                        value="Talking gains you extra money\n"
                              "If it sounds like a logical alias, it probably is\n"
                              "Your health regenerates every minute\n"
                              "The weaponsmith refills his inventory every hour\n"
                              "A boss can be fought at the hour mark",
                        inline=False)
        embed.add_field(name="{}rpg [role|r|class|c]".format(prefix),
                        value="Switch your role on the battlefield (A role is needed to play the game)",
                        inline=False)
        embed.add_field(name="{}rpg [setchannel]".format(prefix),
                        value="This sets the channel for bossbattle results "
                              "(It only needs to be done once per server by an admin)", inline=False)
        await self.bot.send_message(ctx.message.author, embed=embed)

        # RPG infos
        embed = discord.Embed(colour=RPG_EMBED_COLOR)
        embed.set_author(name="RPG Help: Status Information", icon_url=self.bot.user.avatar_url)
        embed.add_field(name="{}rpg [info|i|stats|status] <user>".format(prefix),
                        value="Show your or another user's game statistics", inline=False)
        embed.add_field(name="{}rpg [info|i|stats|status] [weapon|w|armor|a] <user>".format(prefix),
                        value="Show your or another user's weapon statistics", inline=False)
        embed.add_field(name="{}rpg [levelup|lvl|lvlup]".format(prefix),
                        value="Choose a reward when you leveled up", inline=False)
        embed.add_field(name="{}rpg king".format(prefix), value="Show the current King of the server",
                        inline=False)
        embed.add_field(name="{}rpg king [c|b|challenge|battle]".format(prefix),
                        value="Challenge the current King and try to take his spot (level 10+)", inline=False)
        embed.add_field(name="{}rpg [party|p]".format(prefix),
                        value="Show the brave souls that will be attacking the boss at the hour mark", inline=False)
        embed.add_field(name="{}rpg [top|t] <exp|money|bosstier> <page>".format(prefix),
                        value="Show the best players of the game", inline=False)
        await self.bot.send_message(ctx.message.author, embed=embed)

        # RPG what can you actually do help
        embed = discord.Embed(colour=RPG_EMBED_COLOR)
        embed.set_author(name="RPG Help: Things to do", icon_url=self.bot.user.avatar_url)
        embed.add_field(name="{}rpg [adventure|a] <minutes>".format(prefix),
                        value="Go on an adventure, find monsters to slay to gain exp", inline=False)
        embed.add_field(name="{}rpg [wander|w] <minutes>".format(prefix),
                        value="Go wandering, you might find a great treasure!", inline=False)
        embed.add_field(name="{}rpg [battle|b] <user>".format(prefix),
                        value="Battle another user for the lolz, no exp will be gained and no health will be lost",
                        inline=False)
        embed.add_field(name="{}rpg [join|j]".format(prefix),
                        value="Join the hourly boss raid (warning, don't try this alone)", inline=False)
        await self.bot.send_message(ctx.message.author, embed=embed)

        # Shop/training/work
        embed = discord.Embed(colour=RPG_EMBED_COLOR)
        embed.set_author(name="RPG Help: Improve your character", icon_url=self.bot.user.avatar_url)
        embed.add_field(name="{}shop".format(prefix), value="Show the rpg shop inventory", inline=False)
        embed.add_field(name="{}shop [item|i|buy] <item> <amount>".format(prefix),
                        value="Buy <amount> of <item> from the shop", inline=False)
        embed.add_field(name="{}shop [weapon|w] <number>".format(prefix),
                        value="Buy a certain weapon from the shop (hourly refresh of stock)", inline=False)
        embed.add_field(name="{}shop [armor|a] <number>".format(prefix),
                        value="Buy a certain armor from the shop (hourly refresh of stock)", inline=False)
        embed.add_field(name="{}train".format(prefix), value="Show the available training sessions",
                        inline=False)
        embed.add_field(name="{}train <stat> <amount>".format(prefix),
                        value="Train yourself for <amount> points of the chosen <stat>", inline=False)
        embed.add_field(name="{}work <amount>".format(prefix),
                        value="Work an interesting job for some money, for <amount> minutes", inline=False)
        await self.bot.send_message(ctx.message.author, embed=embed)

        # Pets help
        embed = discord.Embed(colour=RPG_EMBED_COLOR)
        embed.set_author(name="RPG Help: Pets", icon_url=self.bot.user.avatar_url)
        embed.add_field(name="{}rpg [pet,pets] <user>".format(prefix),
                        value="Show the pets owned by you or another user", inline=False)
        embed.add_field(name="{}rpg [pet,pets] [release,remove,r] <pet name>".format(prefix),
                        value="Release all pets with the name <pet name>, be warned, they will be gone forever!",
                        inline=False)
        embed.set_footer(
            text="Suggestions? Feel free to message me or join my server (see {}help for details)".format(
                prefix))
        await self.bot.send_message(ctx.message.author, embed=embed)

    # RPG intro/help
    @commands.group(pass_context=1, aliases=["Rpg", "b&d", "B&d", "bnd", "Bnd"],
                    help="Get send an overview of the rpg game's commands")
    async def rpg(self, ctx):
        if ctx.invoked_subcommand is None and ctx.message.content == '{}rpg'.format(self.bot._get_prefix(ctx.message)):
            if not await self.bot.pre_command(message=ctx.message, command='rpg help'):
                return
            await self.send_help_message(ctx)

    # {prefix}rpg adventure #
    @rpg.command(pass_context=1, help="RPG game help message!", aliases=["Help"])
    async def help(self, ctx):
        if not await self.bot.pre_command(message=ctx.message, command='rpg help'):
            return
        await self.send_help_message(ctx)

    # {prefix}rpg adventure #
    @rpg.command(pass_context=1, aliases=["Adventure", "a", "A"], help="Go on an adventure!")
    async def adventure(self, ctx, *args):
        if not await self.bot.pre_command(message=ctx.message, command='rpg adventure'):
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if not await self.check_role(data.role, ctx.message):
            return
        if len(args) > 0:
            try:
                n = int(args[0])
            except ValueError:
                n = 10
        else:
            n = 10
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if data.busydescription != rpgchar.BUSY_DESC_NONE:
            await self.bot.say("You are already doing other things")
            return
        if n < rpgchar.minadvtime:
            await self.bot.say("You came back before you even went out, 0 exp earned")
            return
        if n > (rpgchar.maxadvtime + data.extratime):
            await self.bot.say(
                "You can only go on an adventure for {} minutes".format(rpgchar.maxadvtime + data.extratime))
            return
        c = ctx.message.channel
        if c.is_private:
            c = ctx.message.author
        data.set_busy(rpgchar.BUSY_DESC_ADVENTURE, n, c.id)
        await self.bot.say(
            "{}, you are now adventuring for {} minutes, good luck!".format(ctx.message.author.mention, n))

    # {prefix}rpg battle <user>
    @rpg.command(pass_context=1, aliases=["Battle", "b", "B"], help="Battle a fellow discord ally to a deadly fight!")
    async def battle(self, ctx, *args):
        if not await self.bot.pre_command(message=ctx.message, command='rpg battle'):
            return
        attacker = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if not await self.check_role(attacker.role, ctx.message):
            return
        try:
            errors = {'no_mention': "You need to tag someone to battle with!"}
            defender = await self.bot.get_member_from_message(message=ctx.message, args=args, in_text=True,
                                                              errors=errors)
        except ValueError:
            return

        if defender == ctx.message.author:
            await self.bot.say("Suicide is never the answer :angry:")
            return

        defender = self.get_player_data(defender.id, name=defender.display_name)
        await self.resolve_battle("Mockbattle", ctx.message.channel, [attacker], [defender],
                                  thumbnail=ctx.message.author.avatar_url)

    # {prefix}rpg info [weapon|w|armor|a] <user>
    @rpg.command(pass_context=1, aliases=["Info", "I", 'i', 'stats', "Stats", 'status', "Status"],
                 help="Show the character's status information!")
    async def info(self, ctx, *args):
        if not await self.bot.pre_command(message=ctx.message, command='rpg info'):
            return

        try:
            if len(args) > 0 and args[0] in ['w', 'weapon', 'a', 'armor']:
                a = args[1:]
            else:
                a = args
            user = await self.bot.get_member_from_message(message=ctx.message, args=a, errors=None, in_text=True)
        except ValueError:
            user = ctx.message.author

        data = self.get_player_data(user.id, name=user.display_name)
        if data.role not in [x[0] for x in rpgc.names.get("role")]:
            await self.bot.say("{}, that player is still Undead. Please select a class with "
                               "'{}rpg role' in order to start to play!".format(ctx.message.author.mention,
                                                                                self.bot._get_prefix(ctx.message)))
            return

        # Requested info is of weapon
        if len(args) > 0:
            if args[0] in ['w', 'weapon']:
                embed = discord.Embed(colour=RPG_EMBED_COLOR)
                embed.set_author(name="{}'s weapon".format(data.name), icon_url=ctx.message.author.avatar_url)
                embed.add_field(name="Weapon's name", value=data.weapon.name, inline=False)
                embed.add_field(name="Original cost", value=data.weapon.cost, inline=False)
                embed.add_field(name="Element", value=rpgc.elementnames.get(data.weapon.element)[0], inline=False)
                if data.weapon.damage != 0:
                    embed.add_field(name="Damage", value=data.weapon.damage, inline=False)
                if data.weapon.weaponskill != 0:
                    embed.add_field(name="Weaponskill", value=data.weapon.weaponskill, inline=False)
                if data.weapon.critical != 0:
                    embed.add_field(name="Critical", value=data.weapon.critical, inline=False)
                await self.bot.send_message(ctx.message.channel, embed=embed)
                return

            # Requested info is of armor
            if args[0] in ['a', 'armor']:
                embed = discord.Embed(colour=RPG_EMBED_COLOR)
                embed.set_author(name="{}'s armor".format(data.name), icon_url=ctx.message.author.avatar_url)
                embed.add_field(name="Armor's name", value=data.armor.name, inline=False)
                embed.add_field(name="Original cost", value=data.armor.cost, inline=False)
                embed.add_field(name="Element", value=rpgc.elementnames.get(data.armor.element)[0], inline=False)
                if data.armor.maxhealth != 0:
                    embed.add_field(name="Maxhealth", value=data.armor.maxhealth, inline=False)
                if data.armor.healthregen != 0:
                    embed.add_field(name="Healthregeneration", value=data.armor.healthregen, inline=False)
                if data.armor.money != 0:
                    embed.add_field(name="Extra money", value="{}%".format(data.armor.money), inline=False)
                await self.bot.send_message(ctx.message.channel, embed=embed)
                return

        # Requested info is of player
        # Load image and set basic params
        try:
            im = Image.open("rpggame/{}.png".format(data.role.lower()))
        except:
            im = Image.open("rpggame/undead.png")
        if ctx.message.channel.is_private:
            url = ctx.message.author.avatar_url
        else:
            url = ctx.message.server.get_member(str(data.userid)).avatar_url
        pp = Image.open(BytesIO(requests.get(url).content))
        pp = pp.resize((60, 60))
        im.paste(pp, (235, 5))

        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype(font_path, 12)
        color = (255, 255, 255)
        nameoffset = 18
        statoffset = nameoffset + 98
        topoffset = 18
        following = 23

        # Gather and add information to the picture
        name = data.name
        if len(name) < 12:
            name += " 's informations"
        draw.text((nameoffset, topoffset), name + ":", color, font=font)
        draw.text((nameoffset, topoffset + following), str(data.role), color, font=font)
        if data.levelups > 0:
            stats = "Level up available!"
        else:
            if data.exp > 1000000000:
                shortexp = str(int(data.exp / 1000000000)) + "B"
            elif data.exp > 1000000:
                shortexp = str(int(data.exp / 1000000)) + "M"
            elif data.exp > 1000:
                shortexp = str(int(data.exp / 1000)) + "K"
            else:
                shortexp = str(int(data.exp))
            stats = "lvl {} ({} xp)".format(data.get_level(), shortexp)
        draw.text((statoffset, topoffset + following), stats, color, font=font)
        draw.text((nameoffset, topoffset + 2 * following), "Boss Tier:", color, font=font)
        draw.text((statoffset, topoffset + 2 * following), "{}".format(data.get_bosstier()), color, font=font)
        if data.health <= 0:
            stats = "Dead"
        elif data.busydescription == rpgchar.BUSY_DESC_ADVENTURE:
            stats = "Adventuring for {}m".format(data.busytime)
        elif data.busydescription == rpgchar.BUSY_DESC_TRAINING:
            stats = "Training for {}m".format(data.busytime)
        elif data.busydescription == rpgchar.BUSY_DESC_BOSSRAID:
            stats = "Waiting for the bossbattle"
        elif data.busydescription == rpgchar.BUSY_DESC_WANDERING:
            stats = "Wandering for {}m".format(data.busytime)
        elif data.busydescription == rpgchar.BUSY_DESC_WORKING:
            stats = "Working for {}m".format(data.busytime)
        else:
            stats = "Alive"
        draw.text((nameoffset, topoffset + 3 * following), "Status:", color, font=font)
        draw.text((statoffset, topoffset + 3 * following), stats, color, font=font)
        draw.text((nameoffset, topoffset + 4 * following), "Money:", color, font=font)
        draw.text((statoffset, topoffset + 4 * following), "{}{}".format(rpggameactivities.money_sign, data.money),
                  color,
                  font=font)
        draw.text((nameoffset, topoffset + 5 * following), "Health:", color, font=font)
        draw.text((statoffset, topoffset + 5 * following), "{}/{}".format(data.health, data.get_max_health()), color,
                  font=font)
        draw.text((nameoffset, topoffset + 6 * following), "Damage:", color, font=font)
        draw.text((statoffset, topoffset + 6 * following), "{}".format(data.get_damage()), color, font=font)
        draw.text((nameoffset, topoffset + 7 * following), "Weaponskill:", color, font=font)
        draw.text((statoffset, topoffset + 7 * following), "{}".format(data.get_weaponskill()), color, font=font)
        draw.text((nameoffset, topoffset + 8 * following), "Critical:", color, font=font)
        draw.text((statoffset, topoffset + 8 * following), "{}".format(data.get_critical()), color, font=font)
        draw.text((nameoffset, topoffset + 9 * following), "Time extention:", color, font=font)
        draw.text((statoffset, topoffset + 9 * following), "{}".format(data.extratime), color, font=font)
        draw.text((nameoffset, topoffset + 10 * following), "Pets:", color, font=font)
        draw.text((statoffset, topoffset + 10 * following), "{}".format(len(data.pets)), color, font=font)

        imname = 'temp/{}.png'.format(ctx.message.author.id)
        im.save(imname)
        await self.bot.send_file(ctx.message.channel, imname)
        os.remove(imname)

    # {prefix}rpg join
    @rpg.command(pass_context=1, aliases=["Join", "J", "j"], help="Join a raid to kill a boss!")
    async def join(self, ctx):
        if not await self.bot.pre_command(message=ctx.message, command='rpg join'):
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if not await self.check_role(data.role, ctx.message):
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if data.busydescription != rpgchar.BUSY_DESC_NONE:
            await self.bot.say("{}, finish your current task first, then you can join the boss raid party!".format(
                ctx.message.author.mention))
            return
        if ctx.message.channel.is_private:
            await self.bot.say("This command cannot work in a private channel")
            return
        party = self.get_party(ctx.message.server.id)
        if data in party:
            await self.bot.say("{}, you are already in the boss raid party...".format(ctx.message.author.mention))
            return
        if len(party) <= 0 and not dbcon.get_rpg_channel(ctx.message.server.id):
            await self.bot.say('Be sure to set the channel for bossfights with "{}rpg setchannel, '
                               'or you will not be able to see the results!'.format(self.bot._get_prefix(ctx.message)))
        party.append(data)
        data.set_busy(rpgchar.BUSY_DESC_BOSSRAID, 1, ctx.message.server.id)
        await self.bot.say(
            "{}, prepare yourself! You and your party of {} will be fighting the boss at the hour mark!".format(
                ctx.message.author.mention, len(party)))

    # {prefix}rpg king
    @rpg.command(pass_context=1, aliases=["King", "k", "K"], help="The great king's game!")
    async def king(self, ctx, *args):
        kingname = "OMEGA dank L0rD on the ServEr to get all the loli traps"
        if not await self.bot.pre_command(message=ctx.message, command='rpg king'):
            return
        if ctx.message.channel.is_private:
            await self.bot.say("This command cannot work in a private channel")
            return
        king = dbcon.getKing(ctx.message.server.id)
        if len(args) <= 0:
            if king is None:
                await self.bot.say("There is currently no {} in {}".format(kingname, ctx.message.server.name))
                return
            await self.bot.say("The current {} of {} is {}".format(kingname, ctx.message.server.name,
                                                                   ctx.message.server.get_member(
                                                                       str(king)).display_name))
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if data.busydescription != rpgchar.BUSY_DESC_NONE:
            await self.bot.say("Please finish what you are doing before a fight")
            return
        now = datetime.datetime.now()
        if data.kingtimer != 0:
            if (now - datetime.datetime.fromtimestamp(data.kingtimer)).seconds < 3600:
                await self.bot.say(
                    "You are still tired from your last battle, rest for an hour or so and you can try again")
                return
        if dbcon.isKing(data.userid):
            await self.bot.say("You are already a {} of another world".format(kingname))
            return
        if not (args[0] in ["c", "b", "challenge", "battle"]):
            return
        if data.get_level() < 10:
            await self.bot.say("You need to be at least level 10 to challenge the current {}".format(kingname))
            return
        if king is None:
            dbcon.setKing(data.userid, ctx.message.server.id)
            await self.bot.say(
                "You are now the {0} of {1}!\nLong live the {0}!".format(kingname, ctx.message.server.name))
            return
        if king == data.userid:
            await self.bot.say("But you are already the {} of {}...".format(kingname, ctx.message.server.name))
            return
        kingdata = self.get_player_data(king)
        if (await self.resolve_battle("Kingsbattle", ctx.message.channel, [data], [kingdata])) == 1:
            winner = data
            dbcon.setKing(data.userid, ctx.message.server.id)
            await self.bot.say(
                "{0} beat down {1}\n{0} is now the {2} of {3}!".format(data.name, kingdata.name, kingname,
                                                                       ctx.message.server.name))
        else:
            winner = kingdata
            await self.bot.say(
                "{0} beat down {1}\n{0} remains the true {2} of {3}!".format(kingdata.name, data.name, kingname,
                                                                             ctx.message.server.name))
        data.kingtimer = now.timestamp()
        kingdata.kingtimer = now.timestamp()
        winner.health = winner.get_max_health()
        winner.levelups += 1

    async def add_levelup(self, data, channel, reward):
        if reward == 1:
            data.set_max_health(data.maxhealth + 80)
            await self.bot.send_message(channel, "Your base maximum health is now {}".format(data.maxhealth))
        elif reward == 2:
            data.extratime += 1
            await self.bot.send_message(channel, "You can now do things {} minutes longer".format(data.extratime))
        elif reward == 3:
            data.damage += 30
            await self.bot.send_message(channel, "Your base damage is now {}".format(data.damage))
        else:
            await self.bot.send_message(channel, "Dunno what you mean tbh")
            return False
        return True

    # {prefix}rpg levelup
    @rpg.command(pass_context=1, aliases=["Levelup", "lvlup", "Lvlup", "lvl", "Lvl"],
                 help="Choose the rreward for leveling up!")
    async def levelup(self, ctx, *args):
        if not await self.bot.pre_command(message=ctx.message, command='rpg levelup'):
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if not await self.check_role(data.role, ctx.message):
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if data.levelups <= 0:
            await self.bot.say("You have no level-ups available")
            return

        if len(args) <= 0:
            while data.levelups > 0:
                m = await self.bot.say("Available rewards are:\n1)\t+80 hp\n2)\t+1 minute busytime\n3)\t+30 damage")
                r = await self.bot.wait_for_message(timeout=60, author=ctx.message.author, channel=ctx.message.channel)
                await self.bot.delete_message(m)
                if not r:
                    return
                try:
                    num = int(r.content)
                    if await self.add_levelup(data, ctx.message.channel, num):
                        data.levelups -= 1
                    await self.bot.delete_message(r)
                except ValueError:
                    return
        else:
            try:
                if await self.add_levelup(data, ctx.message.channel, int(args[0])):
                    data.levelups -= 1
            except ValueError:
                await self.bot.say("Thats not even a number...")
                return

    # {prefix}rpg leave
    @rpg.command(pass_context=1, aliases=['Leave', 'Retreat', "retreat"],
                 help="leave the boss raid squad!")
    async def leave(self, ctx):
        if not await self.bot.pre_command(message=ctx.message, command='rpg leave'):
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if data.busydescription != rpgchar.BUSY_DESC_BOSSRAID or data not in [j for i in self.boss_parties.values() for
                                                                              j in i]:
            await self.bot.say('You arent even in a bossraid anywhere...')
            return

        data.reset_busy()
        for party in self.boss_parties.keys():
            if data in self.boss_parties.get(party, []):
                self.boss_parties.get(party, []).remove(data)

        await self.bot.say('You have retreated from the bossbattle, for now...')

    # {prefix}rpg party
    @rpg.command(pass_context=1, aliases=["Party", "p", "P"], help="All players gathered to kill the boss")
    async def party(self, ctx):
        if not await self.bot.pre_command(message=ctx.message, command='rpg party', cannot_be_private=True):
            return
        party = self.get_party(ctx.message.server.id)
        if len(party) <= 0:
            await self.bot.say("There is no planned boss raid, but you are welcome to start a party!")
            return
        embed = discord.Embed(colour=RPG_EMBED_COLOR)
        embed.add_field(name="Boss raiding party", value="{} adventurers".format(len(party)), inline=False)
        embed.add_field(name="Estimated boss level", value=max([x.get_bosstier() for x in party]), inline=False)
        m = ""
        for n in party:
            member = ctx.message.server.get_member(str(n.userid))
            m += "{}, level {}\n".format(member.display_name, n.get_level())
        embed.add_field(name="Adventurers", value=m, inline=False)
        await self.bot.say(embed=embed)

    # {prefix}rpg role
    @rpg.command(pass_context=1, aliases=["Role", "r", "R", "class", "Class", "c", "C"],
                 help="Switch your role on the battlefield")
    async def role(self, ctx, *args):
        if not await self.bot.pre_command(message=ctx.message, command='rpg role'):
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if len(args) <= 0:
            embed = discord.Embed(colour=RPG_EMBED_COLOR)
            embed.set_author(name="You can be anything you want, as long as it is one of these:",
                             icon_url=ctx.message.author.avatar_url)
            for name, desc in rpgc.names.get("role"):
                embed.add_field(name=name, value=desc, inline=False)
            embed.set_footer(text="Be aware! You choose you occupation for life!")
            await self.bot.say(embed=embed)
            return
        if data.role in [x[0] for x in rpgc.names.get("role")[:-1]] and ctx.message.author.id != constants.NYAid:
            await self.bot.say('You cannot change your role once chosen')
            return
        role = " ".join(args).lower()
        role = role[0].upper() + role[1:]

        if role == data.role:
            await self.bot.say("{}, that is already your current role...".format(ctx.message.author.mention))
            return
        if role not in [x[0] for x in rpgc.names.get("role")]:
            await self.bot.say("{}, that is not a role available to a mere mortal".format(ctx.message.author.mention))
            return
        if data.role == rpgc.names.get('role')[-1][0]:
            data.health = 100
        data.role = role
        await self.bot.say("{}, you now have the role of {}".format(ctx.message.author.mention, role))

    @staticmethod
    def get_group(s: str):
        if s in ['m', 'money']:
            return "money"
        if s in ['b', 'bt', 'bosstier']:
            return "bosstier"
        if s in ['c', 'critical']:
            return 'critical'
        if s in ['ws', 'weaponskill']:
            return 'weaponskill'
        if s in ['d', 'dam', 'damage']:
            return 'damage'
        if s in ['hp', 'health', 'mh', 'mhp', 'maxhealth']:
            return 'maxhealth'
        return "exp"

    def top_board(self, page=0, group='exp'):
        users_per_page = 10
        embed = discord.Embed(colour=RPG_EMBED_COLOR)
        embed.add_field(name="RPG top players", value="Page " + str(page + 1), inline=False)
        dbcon.update_players(self.players.values())
        player_list = dbcon.get_top_players(self.bot, group, (page + 1) * users_per_page)
        if len(player_list) < (users_per_page * page):
            raise ValueError(math.ceil(len(player_list) / users_per_page))
        top_end = (users_per_page * (page + 1))
        if top_end > len(player_list):
            top_end = len(player_list)
        top_start = (users_per_page * page)
        result = ""

        players = player_list[top_start:top_end]

        for i in range(len(players)):
            name, player_score = players[i]
            rank = page * users_per_page + i + 1
            if group == "money":
                result += "Rank {}:\n\t**{}**, {}{}\n".format(rank, name,
                                                              rpggameactivities.money_sign, player_score)
            elif group == "bosstier":
                result += "Rank {}:\n\t**{}**, tier {}\n".format(rank, name, player_score)
            elif group in ["critical", "weaponskill", "damage", "maxhealth"]:
                result += "Rank {}:\n\t**{}**, {}\n".format(rank, name, player_score)
            else:
                result += "Rank {}:\n\t**{}**, {}xp (L{})\n".format(rank, name, player_score,
                                                                    RPGPlayer.get_level_by_exp(player_score))
        embed.add_field(name="Ranks and names", value=result)
        return embed

    async def handle_reaction(self, reaction: discord.Reaction):
        if reaction.message.id in [x[0] for x in self.top_lists.values()]:
            _, page, group = self.top_lists.get(reaction.message.server.id)
            if reaction.emoji == '\N{LEFTWARDS BLACK ARROW}':
                page = page - 1
            if reaction.emoji == "\N{BLACK RIGHTWARDS ARROW}":
                page = page + 1
            for m in await self.bot.get_reaction_users(reaction):
                if m.id != self.bot.user.id:
                    await self.bot.remove_reaction(reaction.message, reaction.emoji, m)
            try:
                embed = self.top_board(page, group)
                await self.bot.edit_message(reaction.message, embed=embed)
                self.top_lists[reaction.message.server.id] = (reaction.message.id, page, group)
            except ValueError:
                pass

    # {prefix}rpg top <exp|money|bosstier> <amount>
    @rpg.command(pass_context=1, aliases=["Top", "T", 't'], help="Show the people with the most experience!")
    async def top(self, ctx, *args):
        if not await self.bot.pre_command(message=ctx.message, command='rpg top'):
            return
        if len(args) > 0:
            if len(args) > 1:
                try:
                    n = int(args[1]) - 1
                except ValueError:
                    n = 0
                group = RPGGame.get_group(args[0])
            else:
                try:
                    n = int(args[0]) - 1
                    group = "exp"
                except ValueError:
                    n = 0
                    group = RPGGame.get_group(args[0])
        else:
            n = 0
            group = "exp"

        try:
            embed = self.top_board(page=n, group=group)
        except ValueError as e:
            await self.bot.say("There are only {} pages...".format(str(e)))
            return
        m = await self.bot.send_message(ctx.message.channel, embed=embed)
        await self.bot.add_reaction(m, '\N{LEFTWARDS BLACK ARROW}')
        await self.bot.add_reaction(m, "\N{BLACK RIGHTWARDS ARROW}")
        await self.bot.add_reaction(m, "\N{BROKEN HEART}")
        self.top_lists[ctx.message.server.id] = (m.id, n, group)

    # {prefix}rpg wander #
    @rpg.command(pass_context=1, aliases=["Wander", "w", "W"], help="Wander in the beautiful country")
    async def wander(self, ctx, *args):
        if not await self.bot.pre_command(message=ctx.message, command='rpg wander'):
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if not await self.check_role(data.role, ctx.message):
            return
        if len(args) > 0:
            try:
                n = int(args[0])
            except ValueError:
                n = 10
        else:
            n = 10
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        if data.busydescription != rpgchar.BUSY_DESC_NONE:
            await self.bot.say("You are already doing other things")
            return
        if not (rpgchar.minwandertime <= n <= (rpgchar.maxwandertime + (2 * data.extratime))):
            await self.bot.say(
                "You can wander between {} and {} minutes".format(rpgchar.minwandertime,
                                                                  rpgchar.maxwandertime + (2 * data.extratime)))
            return
        c = ctx.message.channel
        if c.is_private:
            c = ctx.message.author
        data.set_busy(rpgchar.BUSY_DESC_WANDERING, n, c.id)
        await self.bot.say("{}, you are now wandering for {} minutes, good luck!".format(ctx.message.author.mention, n))

    # DB commands            
    @rpg.command(pass_context=1, hidden=True, help="Reset channels!")
    async def updatedb(self, ctx):
        if not await self.bot.pre_command(message=ctx.message, command='rpg updatedb'):
            return
        if not (ctx.message.author.id == constants.NYAid or ctx.message.author.id == constants.KAPPAid):
            await self.bot.say("Hahahaha, no")
            return
        dbcon.update_players(self.players.values())
        self.players = {}

    @rpg.command(pass_context=1, help="Set rpg channel!")
    async def setchannel(self, ctx):
        if not await self.bot.pre_command(message=ctx.message, command='rpg setchannel'):
            return
        perms = ctx.message.channel.permissions_for(ctx.message.author)
        if not (ctx.message.author.id == constants.NYAid or perms.manage_server or perms.administrator):
            await self.bot.say("Hahahaha, no")
            return
        dbcon.set_rpg_channel(ctx.message.server.id, ctx.message.channel.id)
        await self.bot.say("This channel is now the rpg channel for this server")

    # money for devs (testing purpose ONLY)
    @rpg.command(pass_context=1, hidden=True, help="Dev money")
    async def cashme(self, ctx):
        if not await self.bot.pre_command(message=ctx.message, command='rpg cashme', is_typing=False):
            return
        if not (ctx.message.author.id == constants.NYAid or ctx.message.author.id == constants.KAPPAid):
            await self.bot.say("Hahahaha, no")
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        data.money += 99999999

    @rpg.command(pass_context=1, hidden=True)
    async def xpme(self, ctx, amount: int):
        if not await self.bot.pre_command(message=ctx.message, command='rpg xpme', is_typing=False):
            return
        if not (ctx.message.author.id == constants.NYAid or ctx.message.author.id == constants.KAPPAid):
            await self.bot.say("Hahahaha, no")
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        data.exp += amount

    @rpg.command(pass_context=1, hidden=True, aliases=['tbf'])
    async def triggerbossfights(self, ctx):
        if not await self.bot.pre_command(message=ctx.message, command='rpg triggerbossfights', is_typing=False):
            return
        if not (ctx.message.author.id == constants.NYAid or ctx.message.author.id == constants.KAPPAid):
            await self.bot.say("Hahahaha, no")
            return
        await self.bot.rpggame.boss_battle()

    @rpg.command(pass_context=1, hidden=True)
    async def listloadedplayers(self, ctx):
        if not await self.bot.pre_command(message=ctx.message, command='rpg listloadedplayers', is_typing=False):
            return
        if not (ctx.message.author.id == constants.NYAid or ctx.message.author.id == constants.KAPPAid):
            await self.bot.say("Hahahaha, no")
            return
        for player in self.players.values():
            print('{} {}: descr:{} time:{}'.format(player.userid, player.name, player.busydescription, player.busytime))
            for pet in player.pets:
                print('  ', pet.petid, pet.name)

    @rpg.command(pass_context=1, hidden=True)
    async def addpet(self, ctx, num: int):
        if not await self.bot.pre_command(message=ctx.message, command='rpg addpet'):
            return
        if not (ctx.message.author.id == constants.NYAid or ctx.message.author.id == constants.KAPPAid):
            await self.bot.say("Hahahaha, no")
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        for _ in range(num):
            data.add_pet(RPGPet())
        await self.bot.say('{} cats added'.format(num))

    @rpg.command(pass_context=1, hidden=True)
    async def clearpets(self, ctx):
        if not await self.bot.pre_command(message=ctx.message, command='rpg clearpets'):
            return
        if not (ctx.message.author.id == constants.NYAid or ctx.message.author.id == constants.KAPPAid):
            await self.bot.say("Hahahaha, no")
            return
        data = self.get_player_data(ctx.message.author.id, name=ctx.message.author.display_name)
        data.pets = []
        await self.bot.say('Slaughtering pets complete')

    @rpg.command(pass_context=1, aliases=["Pets", "Pet", 'pet'])
    async def pets(self, ctx, *args):
        if not await self.bot.pre_command(message=ctx.message, command='rpg pets'):
            return

        # Get specified player
        if len(ctx.message.mentions) > 0:
            u = ctx.message.mentions[0]
        else:
            u = ctx.message.author
        data = self.get_player_data(u.id, name=u.display_name)

        # Release pets subcommand
        if len(args) > 0 and args[0] in ['remove', 'release', 'r']:
            if len(data.pets) <= 0:
                await self.bot.say('You have no pets to remove...')
                return
            if len(args) <= 1 < len(data.pets):
                await self.bot.say('Please say which pet to remove')
                return
            try:
                num_to_remove = int(args[1]) - 1
            except ValueError:
                await self.bot.say('Thats not a number...')
                return
            if num_to_remove >= len(data.pets):
                await self.bot.say('You do not have that many pets...')
                return
            pet = data.pets[num_to_remove]
            data.pets.remove(pet)
            await self.bot.say('Your pet named {} was released into the wild'.format(pet.name))
            return

        # List pets subcommand
        if len(data.pets) <= 0:
            await self.bot.say(
                'You do not have any cuties at the moment, try defeating a boss and maybe it will leave you a reward!')
            return
        embed = discord.Embed(colour=RPG_EMBED_COLOR)
        embed.set_author(name='{}\'s pets:'.format(u.display_name), url=u.avatar_url)
        for i in range(len(data.pets)):
            pet = data.pets[i]
            if pet.exp > 1000000000:
                shortexp = str(int(pet.exp / 1000000000)) + "B"
            elif pet.exp > 1000000:
                shortexp = str(int(pet.exp / 1000000)) + "M"
            elif pet.exp > 1000:
                shortexp = str(int(pet.exp / 1000)) + "K"
            else:
                shortexp = str(int(pet.exp))
            stats = 'Number: {}\nExp: {} (L{})\nDamage: {}\nWeaponskill: {}'.format(i + 1, shortexp, pet.get_level(),
                                                                                    pet.get_damage(),
                                                                                    pet.get_weaponskill())
            embed.add_field(name=pet.name, value=stats)
        await self.bot.say(embed=embed)

    @rpg.command(pass_context=1, hidden=True, aliases=['resetbusy'])
    async def clearbusy(self, ctx, *args):
        if not await self.bot.pre_command(message=ctx.message, command='rpg clearbusy'):
            return
        if not (ctx.message.author.id == constants.NYAid or ctx.message.author.id == constants.KAPPAid):
            await self.bot.say("Hahahaha, no")
            return
        try:
            user = await self.bot.get_member_from_message(ctx.message, args, in_text=True, errors=None)
        except ValueError:
            user = ctx.message.author
        data = self.get_player_data(user.id, name=user.display_name)
        data.reset_busy()
        await self.bot.say('Busy status of player"{}" reset'.format(user.display_name))
