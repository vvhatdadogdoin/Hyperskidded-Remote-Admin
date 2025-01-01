import discord
import colorama
import os
import time
import asyncio
import threading
import requests
import functools

from discord.ext import commands
from colorama import Fore
from flask import request, jsonify, Flask
from queue import Queue

app = Flask(__name__)

request_queue = [] # the queue

bot = commands.Bot(command_prefix = ">", intents = discord.Intents.all())
url = "https://hyperskidded-remote-admin.onrender.com/"
token = os.environ["HSRA_TOKEN"]

def createSession(channelid, message, sessionname):
  headers = {
    "Authorization": f"Bot {token}",
    "Content-Type": "application/json"
  }

  payload = {
    "name": sessionname,
    "auto_archive_duration": 4320,
    "applied_tags": [],
    "message": {
      "content": message
    }
  }

  response = requests.post(f"https://discord.com/api/v9/channels/{channelid}/threads", headers=headers, json=payload)

def passthroughsessioncheck(): # im making this as a decorator so that it will be easier
  def decorator(func):
    def checksession(channel: discord.TextChannel) -> bool:
      return isinstance(channel, discord.Thread) and channel.name.startswith("hsra-session-")

    @functools.wraps(func)
    async def wrapper(ctx: commands.Context, *args, **kwargs):
      if not await checksession(ctx.channel):
        await ctx.send("This channel is not a session channel.")
        return # would not continue if the channel isnt a session
      
      return await func(ctx, *args, **kwargs) # if it is, then it will just continue
    return wrapper
  return decorator

@app.route("/") ## what will the user see when loading the web server on a browser
def index():
  return """
NOTE: This isn't where you should be, as this is only the API for Hyperksidded Remote Admin.\n
Contact clientruncontext on Discord for any reports or whitelist requests you have.
  """

@app.route("/data-poll", methods=["GET", "POST"]) # something is wrong with the data poll, so i had to debug it
def pollfordata():
  start_time = time.time()
  print(f"[{Fore.GREEN}Web server{Fore.RESET}]: Data poll has started.")
  
  while time.time() - start_time < 30:
    # print(f"[{Fore.GREEN}Web server{Fore.RESET}]: Current queue state", list(request_queue.queue))

    if request_queue:
      data = request_queue.pop(0)
      print(f"[{Fore.GREEN}HWeb server{Fore.RESET}]: Recieved data: {data}")
      return jsonify({"status": "data_received", "params": data})
      
    time.sleep(0.5)
  
  return jsonify({"status": "no_data", "params": None})

@app.route("/send-data", methods=["POST"]) ## the endpoint used to send data to the long poll
def senddata():
  try:
    data = request.get_json()
    if not data: # will throw a valueerror if this has invalid json data
      raise ValueError("Invalid JSON data.")
    
    # will add the data to the queue if its a valid json
    request_queue.append(data)
    return jsonify({"status": "data_recieved", "message": "Data recieved."}), 200
  except Exception as e:
    # but will not add the data to the queue if something unexpected happens
    return jsonify({"status": "error", "message": str(e)}), 400
  
@app.route("/create-session", methods=["POST"])
def createsession():
  try:
    data = request.get_json()
    if not data:
      raise ValueError("Invalid JSON data")
    
    channelid = int(data.get("channel_id")) # on the lua side, i would get an warning that the channel id surpasses the 64-bit integer limit, so i made the lua side send the channel id as a string and once the webserver recieves the string it will convert it back to an integer
    message = data.get("message")
    sessionname = data.get("session_name")

    createSession(channelid = channelid, message = message, sessionname = sessionname)

    return jsonify({"status": "success"}), 200
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 400

def main1():
  app.run(host = "0.0.0.0", port = 5000, debug = False, use_reloader = False)

  
@bot.event
async def on_connect():
  print(f"[{Fore.GREEN}Hyperskidded Remote Admin{Fore.RESET}]: Bot has successfully connected to Discord.")
  await bot.change_presence(status = discord.Status.dnd, activity = discord.Activity(type=discord.ActivityType.watching, name="stalin giving communist orders"))

@bot.event
async def on_command_error(ctx, error):
  try:
    await ctx.message.delete()
  except Exception as err:
    embed = discord.Embed(
        color = discord.Color.red(),
        title = "Error",
        description = "An unexpected error has occured."
    )
    embed.add_field(name="Details", value=err, inline=False)
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
    await ctx.send(embed=embed)

  if isinstance(error, commands.CommandNotFound):
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "This command isn't valid."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)
    print(f"[{Fore.GREEN}Hyperskidded Remote Admin{Fore.RESET}]: Invalid command ran: {ctx.message.content}")

  if isinstance(error, commands.CheckFailure):
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "You do not have the necessary permissions to use this command."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)

  if isinstance(error, commands.BadArgument):
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "Invalid arguments were provided to the command."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)

  if isinstance(error, commands.MissingRequiredArgument):
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "Missing arguments were provided to the command."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)

@bot.event
async def on_command(ctx):
  try:
    await ctx.message.delete()
  except Exception as err:
    print(f"[{Fore.GREEN}Hyperskidded Remote Admin{Fore.RESET}]: Error while deleting command message: {err}")
      
  print(f"[{Fore.GREEN}Hyperskidded Remote Admin{Fore.RESET}]: Command ran: {ctx.command}")

@bot.command(aliases=["commands"])
async def cmds(ctx):
  await ctx.send("""
**Hyperskidded Remote Admin** - Commands
> `>cmds` - Shows this message
> `>cm` - Sends a message to every running server in the game, name displayed.
> `>csm` - Sends a message to every running server in the game, name not displayed.
> `>ban` - Server bans the specified user from the game temporarily.
    """)

@bot.command(aliases=["chatmessage", "cmessage", "chatm"])
async def cm(ctx, *, message):
  if not isinstance(ctx.channel, discord.Thread) and not ctx.channel.name.startswith("hsra-session-"):
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "This channel is not a session channel."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)
    return # would not continue if the channel isnt a session
  else:
    data = {
      "Action": "sendchatannouncement1",
      "Message": message,
      "User": ctx.message.author.name,
      "Session": ctx.channel.name
    }

    try:
      requests.post(url + "send-data", json=data, timeout = 40)
      embed = discord.Embed(
        color = discord.Color.green(),
        title = "Success",
        description = "Successfully sent message to the session."
      )
      embed.add_field(name="Message", value=message, inline=False)
      embed.timestamp = discord.utils.utcnow()
      embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
      await ctx.send(embed=embed)
    except Exception as err:
      embed = discord.Embed(
        color = discord.Color.red(),
        title = "Error",
        description = "An unexpected error has occured."
      )
      embed.add_field(name="Details", value=err, inline=False)
      embed.timestamp = discord.utils.utcnow()
      embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
      await ctx.send(embed=embed)

@bot.command(aliases=["chatsystemmessage", "csystemmessage", "csmessage"])
async def csm(ctx, *, message):
  if not isinstance(ctx.channel, discord.Thread) and not ctx.channel.name.startswith("hsra-session-"):
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "This channel is not a session channel."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)
    return
  else:
    data = {
      "Action": "sendchatannouncement2",
      "Message": message,
      "User": ctx.message.author.name,
      "Session": ctx.channel.name
    }

    try:
      requests.post(url + "send-data", json=data, timeout = 40)
      embed = discord.Embed(
        color = discord.Color.green(),
        title = "Success",
        description = "Successfully sent message to the session."
      )
      embed.add_field(name="Message", value=message, inline=False)
      embed.timestamp = discord.utils.utcnow()
      embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
      await ctx.send(embed=embed)
    except Exception as err:
      embed = discord.Embed(
        color = discord.Color.red(),
        title = "Error",
        description = "An unexpected error has occured."
      )
      embed.add_field(name="Details", value=err, inline=False)
      embed.timestamp = discord.utils.utcnow()
      embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
      await ctx.send(embed=embed)

@bot.command()
async def ban(ctx, player, *, message):
  if not isinstance(ctx.channel, discord.Thread) and not ctx.channel.name.startswith("hsra-session-"):
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "This channel is not a session channel."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)
    return
  else:
    data = {
      "Action": "ban",
      "Reason": message,
      "Player": player,
      "Session": ctx.channel.name
    }
  
    try:
      requests.post(url + "send-data", json=data, timeout = 40)
      embed = discord.Embed(
        color = discord.Color.green(),
        title = "Success",
        description = "Successfully banned player from session."
      )
      embed.add_field(name="Player", value=player, inline=True)
      embed.add_field(name="Reason", value=message, inline=True)
      embed.timestamp = discord.utils.utcnow()
      embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
      await ctx.send(embed=embed)
    except Exception as err:
      embed = discord.Embed(
        color = discord.Color.red(),
        title = "Error",
        description = "An unexpected error has occured."
      )
      embed.add_field(name="Details", value=err, inline=False)
      embed.timestamp = discord.utils.utcnow()
      embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
      await ctx.send(embed=embed)

@bot.command()
async def kick(ctx, player, *, message):
  if not isinstance(ctx.channel, discord.Thread) and not ctx.channel.name.startswith("hsra-session-"):
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "This channel is not a session channel."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)
    return
  else:
    data = {
      "Action": "kick",
      "Reason": message,
      "Player": player,
      "Session": ctx.channel.name
    }
  
    try:
      requests.post(url + "send-data", json=data, timeout = 40)
      embed = discord.Embed(
        color = discord.Color.green(),
        description = "Successfully kicked player from session.",
        title = "Success"
      )
      embed.add_field(name="Player", value=player, inline=True)
      embed.add_field(name="Reason", value=message, inline=True)
      embed.timestamp = discord.utils.utcnow()
      embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
      await ctx.send(embed=embed)
    except Exception as err:
      embed = discord.Embed(
        color = discord.Color.red(),
        title = "Error",
        description = "An unexpected error has occured."
      )
      embed.add_field(name="Details", value=err, inline=False)
      embed.timestamp = discord.utils.utcnow()
      embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
      await ctx.send(embed=embed)

@bot.command(aliases=["cs", "csession"])
async def closesession(ctx):
  if not isinstance(ctx.channel, discord.Thread) and not ctx.channel.name.startswith("hsra-session-"):
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "This channel is not a session channel."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)
    return
  else:
    try:
      embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "This session is closing..."
      )
      embed.timestamp = discord.utils.utcnow()
      embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
      await ctx.send(embed=embed)
      await ctx.channel.delete()
    except Exception as err:
      embed = discord.Embed(
        color = discord.Color.red(),
        title = "Error",
        description = "An unexpected error has occured."
      )
      embed.add_field(name="Details", value=err, inline=False)
      embed.timestamp = discord.utils.utcnow()
      embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
      await ctx.send(embed=embed)

def main2():  
  if __name__ == "__main__":
    bot.run(token)

if __name__ == "__main__": # uses threading to start both the web server and the discord bot in parallel, so that they dont block each other
  webserver = threading.Thread(target=main1, daemon=True)
  admin = threading.Thread(target=main2, daemon=True)

  webserver.start()
  admin.start()

  webserver.join()
  admin.join()
