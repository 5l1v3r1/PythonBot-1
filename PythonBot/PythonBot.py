import asyncio, discord
from discord.ext import commands
from discord.ext.commands import Bot
import constants, datetime, log, logging, message_handler, random, responses, sys

# Basic configs
pi = 3.14159265358979323846264

bot = Bot(command_prefix=commands.when_mentioned_or(">"), pm_help=1)
bot.lastmessage = ""
bot.praise = datetime.datetime.utcnow()
bot.spamlist = []
logging.basicConfig()

@bot.event
async def on_ready():
    print('\nStarted bot')
    print("User: " + bot.user.name)
    print("ID: " + bot.user.id)
    print("Started at: " + datetime.datetime.utcnow().strftime("%H:%M:%S") + "\n")
    if not hasattr(bot, 'uptime'):
        bot.uptime = datetime.datetime.utcnow()
    await bot.change_presence(game=discord.Game(name='with lolis <3'), status=discord.Status.do_not_disturb)

# Add commands
import comm.basic_commands
bot.add_cog(comm.basic_commands.Basics(bot))
import comm.minesweeper
bot.add_cog(comm.minesweeper.Minesweeper(bot))
import comm.music
bot.add_cog(comm.music.Music(bot))
import comm.image_commands
bot.add_cog(comm.image_commands.Images(bot))
import comm.mod_commands
bot.add_cog(comm.mod_commands.Mod(bot))
import rpggame.rpgmain
bot.rpggameinstance = rpggame.rpgmain.RPGgame(bot)
bot.add_cog(bot.rpggameinstance)

# Handle incoming messages
@bot.event
async def on_message(message):
    if (message.author.bot):
        return
    if message.content:
        await message_handler.new(bot, message)
    if len(message.attachments) > 0:
        await message_handler.new_pic(bot, message)
    # Commands in the message
    await bot.process_commands(message)
    #Send message to rpggame for exp
    await bot.rpggameinstance.handle(message)
    bot.lastmessage = message

# Logging
#@bot.event
#async def on_error(event, *args, **kwargs):
#    await log.error(event, args)
@bot.event
async def on_message_edit(before, after):
    await message_handler.edit(before)
@bot.event
async def on_message_delete(message):
    await message_handler.deleted(message)
@bot.event
async def on_member_join(member):
    await log.error(member.server.name + " | Member " + member.name + " just joined")
@bot.event
async def on_member_remove(member):
    await log.error(member.server.name + " | Member " + member.name + " just left")
    embed = discord.Embed(colour=0xFF0000)
    embed.add_field(name="User left", value="\"" + member.name + "\" just left. Byebye, you will not be missed!")
    m = await bot.send_message(member.server.default_channel, embed=embed)
    await asyncio.sleep(30)
    try:
        await self.bot.delete_message(m)
    except discord.Forbidden:
        print(ctx.message.server + " | No permission to delete messages")
@bot.event
async def on_channel_delete(channel):
    await log.error("deleted channel: " + channel.name)
@bot.event
async def on_channel_create(channel):
    await log.error("created channel: " + channel.name)
@bot.event
async def on_channel_update(before, after):
    m = "Channel updated:"
    if before.id != after.id:
        m += " id from: " + before.id + " to: " + after.id
    if before.name != after.name:
        m += " name from: " + before.name + " to: " + after.name
    if before.position != after.position:
        m += " position from: " + before.position + " to: " + after.position
    if before._permission_overwrites != after._permission_overwrites:
        m += " _permission_overwrites changed"
    await log.error(m)
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
        await log.error(m)
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
        m += " region from: " + before.region + " to: " + after.region
    if not m == "server " + before.name + " updated: ":
        await log.error(m)
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
        await log.error(before.server.name + " | " + m)
@bot.event
async def on_server_emojis_update(before, after):
    m = "emojis updated: "
    if len(before) != len(after):
        m += " size from: " + str(len(before)) + " to: " + str(len(after))
    if not m == "emojis " + before.name + " updated: ":
        await log.error(m)
@bot.event
async def on_member_ban(member):
    await log.error("user " + member.name + " banned")
@bot.event
async def on_member_unban(member):
    await log.error("user " + member.name + " unbanned")

# Actually run the bot
bot.run(constants.bot_token)