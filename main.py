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
    "Authorization": f"{token}",
    "Content-Type": "application/json"
  }

  payload = {
    'name': sessionname,
    'type': 11,
    'message': message
  }

  response = requests.post(f"https://discord.com/api/v9/channels/{channelid}/threads?use_nested_fields=true", headers=headers, json=payload)

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
    
    channel_id = int(data.get("channel_id")) # on the lua side, i would get an warning that the channel id surpasses the 64-bit integer limit, so i made the lua side send the channel id as a string and once the webserver recieves the string it will convert it back to an integer
    Message = data.get("message")
    sessionName = data.get("session_name")

    createSession(channelid = channel_id, message = Message, sessionname = sessionName)

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
    print(f"[{Fore.GREEN}Hyperskidded Remote Admin{Fore.RESET}]: Error while deleting command message: {err}")

  if isinstance(error, commands.CommandNotFound):
    await ctx.send(f"Error: {ctx.message.content} is not a valid command.", delete_after = 5)
    print(f"[{Fore.GREEN}Hyperskidded Remote Admin{Fore.RESET}]: Invalid command ran: {ctx.message.content}")

  if isinstance(error, commands.CheckFailure):
    await ctx.send("Error: You do not have the necessary permissions to run this command.", delete_after = 5)

  if isinstance(error, commands.BadArgument):
    await ctx.send("Error: You provided invalid arguments to the specified command.", delete_after = 5)

  if isinstance(error, commands.MissingRequiredArgument):
    await ctx.send("Error: You provided missing arguments to the specified command.", delete_after = 5)

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
    await ctx.send("This channel is not a session channel.")
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
      await ctx.send("Successfully sent message.")
    except Exception as err:
      await ctx.send("Error occured while sending request: " + str(err))

@bot.command(aliases=["chatsystemmessage", "csystemmessage", "csmessage"])
async def csm(ctx, *, message):
  if not isinstance(ctx.channel, discord.Thread) and not ctx.channel.name.startswith("hsra-session-"):
    await ctx.send("This channel is not a session channel.")
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
      await ctx.send("Successfully sent message.")
    except Exception as err:
      await ctx.send("Error occured while sending request: " + str(err))

@bot.command()
async def ban(ctx, player, *, message):
  if not isinstance(ctx.channel, discord.Thread) and not ctx.channel.name.startswith("hsra-session-"):
    await ctx.send("This channel is not a session channel.")
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
      await ctx.send("Successfully banned player from session.")
    except Exception as err:
      await ctx.send("Error occured while sending request: " + str(err))

@bot.command()
async def kick(ctx, player, *, message):
  if not isinstance(ctx.channel, discord.Thread) and not ctx.channel.name.startswith("hsra-session-"):
    await ctx.send("This channel is not a session channel.")
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
      await ctx.send("Successfully kicked player from session.")
    except Exception as err:
      await ctx.send("Error occured while sending request: " + str(err))

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
