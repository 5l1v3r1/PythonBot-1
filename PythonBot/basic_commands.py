import asyncio, datetime, discord, log, responses, send_random, wikipedia
from discord.ext import commands
from discord.ext.commands import Bot
from random import randint

# Normal commands
class Basics:
    def __init__(self, my_bot):
        self.bot = my_bot
        self.bot.fps = self.bot.biri = self.bot.cat = self.bot.cuddle = datetime.datetime.utcnow()

    # {prefix}60
    @commands.command(pass_context=1, help="Help get cancer out of this world!", aliases=["60"])
    async def fps(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            if (datetime.datetime.utcnow() - self.bot.fps).seconds < (2*60):
                return
            self.bot.fps = datetime.datetime.utcnow()
            await send_random.file(self.bot, ctx.message.channel, "60")
        except Exception as e:
            await log.error("cmd fps: " + str(e))

    # {prefix}biribiri
    @commands.command(pass_context=1, help="Waifu == laifu!", aliases=["biri"])
    async def biribiri(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            if (datetime.datetime.utcnow() - self.bot.biri).seconds < (2*60):
                return
            self.bot.biri = datetime.datetime.utcnow()
            await send_random.file(self.bot, ctx.message.channel, "biribiri")
        except Exception as e:
            await log.error("cmd biribiri: " + str(e))
    
    # {prefix}cast <user>
    @commands.command(pass_context=1, help="Cast a spell!")
    async def cast(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            if len(args) <= 0:
                return await self.bot.send_message(ctx.message.channel, ctx.message.author.name + ", you cannot cast without a target...")
            return await self.bot.send_message(ctx.message.channel, ctx.message.author.name + " casted **" + responses.spell[randint(0, len(responses.spell)-1)]
                                               + "** on " + " ".join(args) + ".\n" +  responses.spellresult[randint(0, len(responses.spellresult)-1)])
        except Exception as e:
            await log.error("cmd cast: " + str(e))

    # {prefix}cat
    @commands.command(pass_context=1, help="CATS!")
    async def cat(self, ctx, *args):
        try:
            print("cat")
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden as e:
                print(ctx.message.server + " | No permission to delete messages")
            if (datetime.datetime.utcnow() - self.bot.cat).seconds < (2*60):
                return
            self.bot.cat = datetime.datetime.utcnow()
            await send_random.file(self.bot, ctx.message.channel, "cat")
        except Exception as e:
            await log.error("cmd cat: " + str(e))
    # {prefix}compliment <user>
    @commands.command(pass_context=1, help="Give someone a compliment")
    async def compliment(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            return await send_random.string(self.bot, ctx.message.channel, responses.compliments, " ".join(args))
        except Exception as e:
            await log.error("cmd compliment: " + str(e))
    
    # {prefix}cuddle
    @commands.command(pass_context=1, help="Cuddles everywhere!")
    async def cuddle(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            if (datetime.datetime.utcnow() - self.bot.cuddle).seconds < (2*60):
                return
            self.bot.cuddle = datetime.datetime.utcnow()
            await send_random.file(self.bot, ctx.message.channel, "cuddle")
        except Exception as e:
            await log.error("cmd cuddle: " + str(e))

    # {prefix}ded
    @commands.command(pass_context=1, help="Ded chat reminder!")
    async def ded(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            await send_random.file(self.bot, ctx.message.channel, "ded")
        except Exception as e:
            await log.error("cmd ded: " + str(e))

    # {prefix}delete
    @commands.command(pass_context=1, help="Delete your message automatically in a bit!", aliases=["del", "d"])
    async def delete(self, ctx, *args):
        try:
            s = args[0]
            try: 
                int(s)
            except ValueError:
                s = 20
            s *= 100
            asyncio.sleep(s)
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
        except Exception as e:
            await log.error("cmd delete: " + str(e))

    # {prefix}echo <words>
    @commands.command(pass_context=1, help="I'll be a parrot!")
    async def echo(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            if ctx.message.content == "":
                return await self.bot.send_message(ctx.message.channel, ctx.message.author.mention + " b-b-baka!")
            return await self.bot.send_message(ctx.message.channel, " ".join(args))
        except Exception as e:
            await log.error("cmd echo: " + str(e))

    # {prefix}evaluate <math>
    @commands.command(pass_context=1, aliases=["eval", "calc"], help="Do the math!")
    async def evaluate(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            return await self.bot.send_message(ctx.message.channel, " ".join(args) + " = " + eval(" ".join(args)))
        except Exception as e:
            await log.error("cmd eval: " + str(e))

    # {prefix}face
    @commands.command(pass_context=1, help="Make a random face!")
    async def face(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            await send_random.string(self.bot, ctx.message.channel, responses.faces)
        except Exception as e:
            await log.error("cmd face: " + str(e))

    # {prefix}hug <person>
    @commands.command(pass_context=1, help="Give hugs!")
    async def hug(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            if ctx.message.content == "":
                return await self.bot.send_message(ctx.message.channel, "Trying to give yourself a hug? Haha, so lonely...")
            await send_random.string(self.bot, ctx.message.channel, responses.hug, ctx.message.author.mention, " ".join(args))
        except Exception as e:
            await log.error("cmd hug: " + str(e))

    # {prefix}userinfo <query>
    @commands.command(pass_context=1, help="Get a user's information!", aliases=["user"])
    async def userinfo(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            if len(ctx.message.mentions)<=0:
                user = ctx.message.author
            else:
                user = ctx.message.mentions[0]
            m = "Stats for **" + user.name + "**```"
            if user.bot:
                m += "\nUser is a bot"
            if user.nick:
                m += "\nNickname:       " + user.nick
            m += "\nId:             " + user.id
            m += "\nDiscriminator:  " + user.discriminator
            m += "\nStatus:         " + user.status.name
            if user.game:
                m += "\nGame:           " + str(user.game)
            m += "\nUser Joined at: " + user.joined_at.strftime("%D/%M/%Y at %H:%M:%S")
            m += "\nRoles:          " + user.roles[0].name
            for r in range(1,len(user.roles)):
                m += ", " + user.roles[r].name
            m += "```"
            await self.bot.send_message(ctx.message.channel, m)
        except Exception as e:
            await log.error("cmd userinffo: " + str(e))

    # {prefix}wikipedia <query>
    @commands.command(pass_context=1, help="Search the wiki!", aliases=["wiki"])
    async def wikipedia(self, ctx, *args):
        try:
            try:
                await self.bot.delete_message(ctx.message)
            except discord.Forbidden:
                print(ctx.message.server + " | No permission to delete messages")
            q = " ".join(args)
            if q == "":
                return await self.bot.send_message(ctx.message.channel, "...")
            try:
                s = wikipedia.summary(q, sentences=2)
                return await self.bot.send_message(ctx.message.channel, "Your query **" + q + "** has the following wikipedia result:\n" + s)
            except Exception as e:
                return await self.bot.send_message(ctx.message.channel, "There are too much answers to give you the correct one...")
        except Exception as e:
            await log.error("cmd wiki: " + str(e))