#!/usr/bin/env python3
import asyncio
import discord

from discord.ext.commands import Bot

import constants
import customHelpFormatter
import datetime
import dbconnect
import log
import logging
import message_handler

from secret import secrets

# Basic configs
pi = 3.14159265358979323846264
REMOVE_JOIN_MESSAGE = False
REMOVE_LEAVE_MESSAGE = False


def initCogs(bot):
    # Add commands
    import comm.basic_commands
    bot.add_cog(comm.basic_commands.Basics(bot))
    import comm.minesweeper
    bot.add_cog(comm.minesweeper.Minesweeper(bot))
    import comm.hangman
    bot.add_cog(comm.hangman.Hangman(bot))
    import comm.image_commands
    bot.add_cog(comm.image_commands.Images(bot))
    if bot.MUSIC:
        import musicPlayer
        bot.musicplayer = musicPlayer.MusicPlayer(bot)
        bot.add_cog(bot.musicplayer)
    if bot.RPGGAME:
        import rpggame.rpgmain, rpggame.rpgshop
        bot.rpggame = rpggame.rpgmain.RPGGame(bot)
        bot.rpgshop = rpggame.rpgshop.RPGShop(bot)
        bot.add_cog(bot.rpggame)
        bot.add_cog(bot.rpgshop)
    import comm.mod_commands
    bot.add_cog(comm.mod_commands.Mod(bot))
    import comm.misc_commands
    bot.add_cog(comm.misc_commands.Misc(bot))


class PythonBot(Bot):
    def __init__(self, music=True, rpggame=True):
        self.praise = datetime.datetime.utcnow()

        self.spamlist = []
        self.spongelist = []
        self.dont_delete_commands_servers = []
        self.commands_banned_in_servers = {}
        self.commans_counters = {}

        self.MUSIC = music
        self.RPGGAME = rpggame
        super(PythonBot, self).__init__(command_prefix=secrets.prefix, pm_help=1,
                                        formatter=customHelpFormatter.customHelpFormatter())

    @staticmethod
    def prep_str_for_print(s: str):
        return s.encode("ascii", "replace").decode("ascii")

    async def delete_command_message(self, message):
        try:
            if not message.channel.is_private:
                await self.delete_message(message)
        except discord.Forbidden:
            print("{} | {} | {} | member {}, no perms to delete message: {}".format(
                datetime.datetime.utcnow().strftime("%H:%M:%S"), PythonBot.prep_str_for_print(message.server.name),
                PythonBot.prep_str_for_print(message.channel.name),
                PythonBot.prep_str_for_print(message.author.name),
                PythonBot.prep_str_for_print(message.content)))
        except discord.ext.commands.errors.CommandInvokeError:
            pass

    def command_allowed_in_server(self, command_name: str, serverid: str):
        banned_commands = self.commands_banned_in_servers.get(serverid)
        if not banned_commands:
            # TODO Get banned commands from database
            return True
        return command_name not in banned_commands

    async def pre_command(self, message: discord.Message, command: str, is_typing=True, delete_message=True, can_be_private=True):
        if is_typing:
            await self.send_typing(message.channel)
        if delete_message and message.server.id not in self.dont_delete_commands_servers:
            await self.delete_command_message(message)
        if not can_be_private:
            await self.send_message(message.channel, 'This command cannot be used in private channels')
            return False
        if not self.command_allowed_in_server(command_name=command, serverid=message.server.id):
            return False
        if self.commans_counters.get(command):
            self.commans_counters[command] += 1
        else:
            self.commans_counters[command] = 1
        return True


    async def timeLoop(self):
        await self.wait_until_ready()
        self.running = True
        while self.running:
            time = datetime.datetime.utcnow()

            if self.RPGGAME:
                await self.rpggame.game_tick(time)
            if self.MUSIC:
                await self.musicplayer.music_loop(time)

            endtime = datetime.datetime.utcnow()
            # print("Sleeping for " + str(60-(endtime).second) + "s")
            await asyncio.sleep(60 - endtime.second)

    async def quit(self):
        self.running = False
        if self.RPGGAME:
            self.rpggame.quit()
        if self.MUSIC:
            await self.musicplayer.quit()

    @staticmethod
    def str_cmd(s: str):
        return s.encode("ascii", "replace").decode("ascii")


def init_bot():
    bot = PythonBot()
    logging.basicConfig()
    initCogs(bot)
    bot.loop.create_task(bot.timeLoop())

    @bot.event
    async def on_ready():
        print('\nStarted bot')
        print("User: " + bot.user.name)
        print("Disc: " + bot.user.discriminator)
        print("ID: " + bot.user.id)
        print("Started at: " + datetime.datetime.utcnow().strftime("%H:%M:%S") + "\n")
        if not hasattr(bot, 'uptime'):
            bot.uptime = datetime.datetime.utcnow()
        await bot.change_presence(game=discord.Game(name='with lolis <3'), status=discord.Status.do_not_disturb)

    # Handle incoming events
    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        if message.channel.is_private:
            await log.log("direct message", message.author.name, message.content, "dm")
            for pic in message.attachments:
                await log.message(message, "pic", pic["url"])
        else:
            if (message.server.id == constants.NINECHATid) & (not message.server.get_member(constants.NYAid)):
                print(
                    message.server.name + "-" + message.channel.name + " (" + message.user.name + ") " + message.content)
            if message.content and message.server.id not in constants.bot_list_servers:
                await message_handler.new(bot, message)
        # Commands in the message
        try:
            await bot.process_commands(message)
        except discord.errors.Forbidden:
            bot.send_message(message.channel, 'I\'m sorry, but my permissions do not allow that...')
        # Pics
        if len(message.attachments) > 0:
            await message_handler.new_pic(bot, message)
        # Send message to rpggame for exp
        if bot.RPGGAME:
            await bot.rpggame.handle(message)

    @bot.event
    async def on_message_edit(before, after):
        await message_handler.edit(before)

    @bot.event
    async def on_message_delete(message):
        await message_handler.deleted(message)

    async def on_member_message(member, func_name, text):
        await log.error(member.server.name + " | Member " + member.name + " just " + text, filename=member.server.name,
                        serverid=member.server.id)
        response = dbconnect.get_message(func_name, member.server.id)
        if not response:
            return
        channel, mes = response
        embed = discord.Embed(colour=0xFF0000)
        embed.add_field(name="User {}!".format(bot.str_cmd(text)), value=mes.format(member.mention))
        channel = bot.get_channel(channel)
        if not channel:
            print('CHANNEL NOT FOUND')
            return
        m = await bot.send_message(channel, embed=embed)
        if REMOVE_JOIN_MESSAGE:
            await asyncio.sleep(30)
            try:
                await bot.delete_message(m)
            except discord.Forbidden:
                print(member.server + " | No permission to delete messages")

    @bot.event
    async def on_member_join(member: discord.Member):
        if member.bot:
            return
        await on_member_message(member, "on_member_join", 'joined')

    @bot.event
    async def on_member_remove(member: discord.Member):
        if member.bot:
            return
        await on_member_message(member, "on_member_remove", 'left')

    # @bot.event
    # async def on_voice_state_update(before, after):
    #     if bot.MUSIC:
    #         if before.id == constants.NYAid:
    #             channel = after.voice.voice_channel
    #             if channel and (before.voice.voice_channel != channel):
    #                 state = bot.musicplayer.get_voice_state(before.server)
    #                 if bot.is_voice_connected(before.server):
    #                     if channel == bot.voice_client_in(before.server):
    #                         return
    #                     state.voice = await state.voice.move_to(channel)
    #                 else:
    #                     state.voice = bot.join_voice_channel(channel)

    @bot.event
    async def on_member_update(before, after):
        changed = False
        m = before.server.name + " | member " + before.name + " updated: "
        if before.name != after.name:
            m += " name from: " + before.name + " to: " + after.name
            changed = True
        if before.nick != after.nick:
            changed = True
            if not before.nick:
                m += " nick from nothing to: " + after.nick
            else:
                if not after.nick:
                    m += " nick reset"
                else:
                    m += " nick from: " + before.nick + " to: " + after.nick
        for r in before.roles:
            if not r in after.roles:
                m += " -role: " + r.name
                changed = True
        for r in after.roles:
            if not r in before.roles:
                m += " +role: " + r.name
                changed = True
        if before.avatar != after.avatar:
            m += " avatar changed"
            changed = True
        if changed:
            await log.error(m, filename=before.server.name, serverid=before.server.id)

    @bot.event
    async def on_server_update(before, after):
        m = "server " + before.name + " updated: "
        if before.name != after.name:
            m += " name from: " + before.name + " to: " + after.name
        for r in before.roles:
            if not r in after.roles:
                m += " -role: " + r.name
        for r in after.roles:
            if not r in before.roles:
                m += " +role: " + r.name
        if before.region != after.region:
            m += " region from: " + str(before.region) + " to: " + str(after.region)
        if not m == "server " + before.name + " updated: ":
            await log.error(m, filename=before.name, serverid=before.id)

    @bot.event
    async def on_server_role_update(before, after):
        m = "Role " + before.name + " updated: "
        if before.name != after.name:
            m += " name from: " + before.name + " to: " + after.name
        for r in before.permissions:
            if not r in after.permissions:
                x, y = r
                if y:
                    m += " -permission: " + x
        for r in after.permissions:
            if not r in before.permissions:
                x, y = r
                if y:
                    m += " +permission: " + x
        if not m == "role " + before.name + " updated: ":
            await log.error(m, filename=before.name, serverid=before.server.id)

    @bot.event
    async def on_reaction_add(reaction, user):
        if user.bot:
            return
        if reaction.emoji == "\N{BROKEN HEART}":
            if reaction.message.author.id == bot.user.id:
                await bot.delete_message(reaction.message)
        if bot.musicplayer:
            await bot.musicplayer.handle_reaction(reaction)

    @bot.event
    async def on_member_ban(member: discord.Member):
        await log.error(member.server.name + " | User " + member.name + " banned", filename=member.server.name,
                        serverid=member.server.id)

    @bot.event
    async def on_member_unban(server: discord.Server, user: discord.User):
        await log.error("User " + user.name + " unbanned", filename=server.name, serverid=server.id)

    @bot.event
    async def on_server_join(server: discord.Server):
        user = bot.get_server(constants.PRIVATESERVERid).get_channel(constants.SNOWFLAKE_GENERAL)
        await bot.send_message(user, "I joined a new server named {}, senpai!".format(server.name))

    @bot.event
    async def on_server_remove(server: discord.Server):
        user = bot.get_server(constants.PRIVATESERVERid).get_channel(constants.SNOWFLAKE_GENERAL)
        await bot.send_message(user, "A new server named {} just removed me from service :sadness:".format(server.name))

    return bot


# Start the bot
init_bot().run(secrets.bot_token)
