## NOTE: This may use stuff that are publicly shared by loaders, such as blacklisted require IDs that are blacklisted by Skid Shield, which is provided by SecLoad.

from typing import Text
import discord
import colorama
import os
import time
import asyncio
import threading
import requests

from discord.ext import commands
from colorama import Fore
from flask import request, jsonify, Flask
from queue import Queue

def main1(): ## the flask server
  app = Flask(__name__)

  request_queue = [] # the queue

  @app.route("/") ## what will the user see when loading the web server on a browser
  def index():
    return """
NOTE: This isn't where you should be, as this is only the API for Hyperksidded Remote Admin.\n
Contact clientruncontext for any appeals or whitelist requests you have.
    """

  @app.route("/data-poll", methods=["GET", "POST"]) # something is wrong with the data poll, so i had to debug it
  def pollfordata():
    start_time = time.time()
    print(f"[{Fore.GREEN}Web server{Fore.RESET}]: Data poll has started.")
    
    while time.time() - start_time < 30:
      print(f"[{Fore.GREEN}Web server{Fore.RESET}]: Checking request queue")
      # print(f"[{Fore.GREEN}Web server{Fore.RESET}]: Current queue state", list(request_queue.queue))

      if request_queue:
        data = request_queue.pop(0)
        print(f"[{Fore.GREEN}HWeb server{Fore.RESET}]: Recieved data: {data}")
        return jsonify({"status": "data_received", "params": data})
        
      time.sleep(1)
    
    return jsonify({"status": "no_data", "params": None})

  @app.route("/send-data", methods=["POST"]) ## the endpoint used to send data to the long poll
  def senddata():
    try:
      data = request.get_json()
      if not data: # will throw a valueerror if this has invalid json data
        raise ValueError("Invalid JSON data.")

      # will add the data to the queue if its a valid json
      request_queue.append(data)
      return jsonify({"status": "data_recieved", "message": "Data recieved."})
    except Exception as e:
      # but will not add the data to the queue if something unexpected happens
      return jsonify({"status": "error", "message": str(e)}), 400

  app.run(host = "0.0.0.0", port = 5000, debug = False, use_reloader = False)


def main2(): # the discord bot itself
  bot = commands.Bot(command_prefix = ">", intents = discord.Intents.all())
  url = "https://38fbe3b0-2972-49a8-b3ae-387382344ce2-00-34ks7whjtzntm.kirk.replit.dev/"
  
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
    await ctx.send("Sending message...")

    data = {
      "Action": "sendchatannouncement1",
      "Message": message,
      "User": ctx.message.author.name
    }

    try:
      requests.post(url + "send-data", json=data, timeout = 40)
      await ctx.send("Successfully sent message.")
    except Exception as err:
      await ctx.send("Error occured while sending request: " + str(err))
  

  token = os.environ["HSRA_TOKEN"]
  
  if __name__ == "__main__":
    bot.run(token)


if __name__ == "__main__": # uses threading to start both the web server and the discord bot in parallel, so that they dont block each other
  webserver = threading.Thread(target=main1, daemon=True)
  admin = threading.Thread(target=main2, daemon=True)

  webserver.start()
  admin.start()

  webserver.join()
  admin.join()
