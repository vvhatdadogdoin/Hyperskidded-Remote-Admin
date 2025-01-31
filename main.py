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
from flask import request, jsonify, Flask, abort
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from queue import Queue
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
owner_id = os.getenv('OWNER_ID')
db = SQLAlchemy(app)
migrate = Migrate(app, db)

request_queue = [] # the queue

bot = commands.Bot(command_prefix = ">", intents = discord.Intents.all())
url = "https://hyperskidded-remote-admin.onrender.com/"
token = os.environ["HSRA_TOKEN"]
EXCLUDED_PATHS = ["/data-poll"]

AUTHORIZATION_HEADERS = {
  'Authorization': f'Bearer {token}'
}

class Whitelist(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  discord_user_id = db.Column(db.BigInteger(), unique=True, nullable=False)

  def __repr__(self):
    return f'<Whitelist {self.discord_user_id}>'
  
class BansWhitelist(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  discord_user_id = db.Column(db.BigInteger(), unique=True, nullable=False)

  def __repr__(self):
    return f'<BansWhitelist {self.discord_user_id}>'
  
class HttpBan(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  player_id = db.Column(db.String(100), unique=True, nullable=False)
  reason = db.Column(db.String(255), nullable=False)
  ban_date = db.Column(db.DateTime, default=datetime.utcnow())

  def __repr__(self):
    return f'<HttpBan {self.player_id} banned for {self.reason}>'
  
with app.app_context():
  db.create_all()

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

def passthroughsessioncheck(): # ~~im making this as a decorator so that it will be easier~~ no longer used unfortunately
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

# @app.before_request
# def before_request():
#   securitycheck()

@app.route("/data-poll", methods=["GET", "POST"])
def pollfordata():
  start_time = time.time()
  print(f"[{Fore.GREEN}Web server{Fore.RESET}]: Data poll has started.")
  
  while time.time() - start_time < 30:
    # print(f"[{Fore.GREEN}Web server{Fore.RESET}]: Current queue state", list(request_queue.queue))

    if request_queue:
      data = request_queue.pop(0)
      print(f"[{Fore.GREEN}HWeb server{Fore.RESET}]: Recieved data: {data}")
      return jsonify({"status": "data_received", "params": data}), 200
      
    time.sleep(0.5)
  
  return jsonify({"status": "no_data", "params": None}), 200

@app.route("/whitelist", methods=["POST"])
def whitelist():
  data = request.get_json()
  uid = data.get("user_id")

  if not uid:
    return jsonify({"status": "error", "message": "User Id is not specified."}), 400
  
  api_key = request.headers.get('Authorization')
  if api_key != f'Bearer {token}':
    return jsonify({"status": "authentication_error", "message": "Authentication failed."}), 404
  
  try:
    existing_user = Whitelist.query.filter_by(discord_user_id=uid).first()

    if existing_user:
      return jsonify({"status": "error", "message": "User is already whitelisted."}), 400
    
    new_entry = Whitelist(discord_user_id=uid)
    db.session.add(new_entry)
    db.session.commit()

    return jsonify({"status": "success", "message": "User has been successfully whitelisted."}), 200

  except Exception as err:
    db.session.rollback()
    return jsonify({"status": "error", "message": str(err)}), 500
  
@app.route("/remove-whitelist", methods=["POST"])
def removewhitelist():
  data = request.get_json()
  uid = data.get("user_id")

  if not uid:
    return jsonify({"status": "error", "message": "User Id is required."}), 400
  
  api_key = request.headers.get('Authorization')
  if api_key != f'Bearer {token}':
    return jsonify({"status": "authentication_error", "message": "Authentication failed."}), 404
  
  try:
    existing_user = Whitelist.query.filter_by(discord_user_id=uid).first()

    if not existing_user:
      return jsonify({"status": "error", "message": "User has not been whitelisted."}), 400
    
    db.session.delete(existing_user)
    db.session.commit()

    return jsonify({"status": "success", "message": "Successfully removed user's whitelist."}), 200
  
  except Exception as err:
    db.session.rollback()
    return jsonify({"status": "error", "message": str(err)}), 500
  
@app.route("/get-whitelists", methods=["GET"])
def getwhitelists():
  api_key = request.headers.get('Authorization')
  if api_key != f'Bearer {token}':
    return jsonify({"status": "authentication_error", "message": "Authentication failed."})

  try:
    whitelist_entries = Whitelist.query.all()

    whitelists = [
      {
        "user_id": entry.discord_user_id
      }
      for entry in whitelist_entries
    ]

    return jsonify({"whitelists": whitelists}), 200
  
  except Exception as err:
    return jsonify({"status": "error", "message": str(err)}), 500
  
@app.route("/bans-whitelist", methods=["POST"])
def banswhitelist():
  data = request.get_json()
  uid = data.get("user_id")

  api_key = request.headers.get('Authorization')
  if api_key != f'Bearer {token}':
    return jsonify({"status": "authentication_error", "message": "Authentication failed."}), 404

  if not uid:
    return jsonify({"status": "error", "message": "User Id is not specified."}), 400
  
  try:
    existing_user = BansWhitelist.query.filter_by(discord_user_id=uid).first()

    if existing_user:
      return jsonify({"status": "error", "message": "User is already bans whitelisted."}), 400
    
    new_entry = BansWhitelist(discord_user_id=uid)
    db.session.add(new_entry)
    db.session.commit()

    return jsonify({"status": "success", "message": "User has been successfully whitelisted to use banning commands."}), 200

  except Exception as err:
    db.session.rollback()
    return jsonify({"status": "error", "message": str(err)}), 500
  
@app.route("/remove-bans-whitelist", methods=["POST"])
def removebanswhitelist():
  data = request.get_json()
  uid = data.get("user_id")

  api_key = request.headers.get('Authorization')
  if api_key != f'Bearer {token}':
    return jsonify({"status": "authentication_error", "message": "Authentication failed."}), 404

  if not uid:
    return jsonify({"status": "error", "message": "User Id is required."}), 400
  
  try:
    existing_user = BansWhitelist.query.filter_by(discord_user_id=uid).first()

    if not existing_user:
      return jsonify({"status": "error", "message": "User has not been whitelisted to use banning commands."}), 400
    
    db.session.delete(existing_user)
    db.session.commit()

    return jsonify({"status": "success", "message": "Successfully removed user's ban whitelist."}), 200
  
  except Exception as err:
    db.session.rollback()
    return jsonify({"status": "error", "message": str(err)}), 500
  
@app.route("/get-bans-whitelists", methods=["GET"])
def getbanswhitelists():
  api_key = request.headers.get('Authorization')
  if api_key != f'Bearer {token}':
    return jsonify({"status": "authentication_error", "message": "Authentication failed."}), 404

  try:
    bans_whitelist_entries = BansWhitelist.query.all()

    bans_whitelists = [
      {
        "user_id": entry.discord_user_id
      }
      for entry in bans_whitelist_entries
    ]

    return jsonify({"ban_whitelists": bans_whitelists}), 200
  
  except Exception as err:
    return jsonify({"status": "error", "message": str(err)}), 500

@app.route("/send-data", methods=["POST"]) ## the endpoint used to send data to the long poll
def senddata():
  api_key = request.headers.get('Authorization')
  if api_key != f'Bearer {token}':
    return jsonify({"status": "authentication_error", "message": "Authentication failed."}), 404
  
  try:
    data = request.get_json()
    if not data: # will throw a valueerror if this has invalid json data
      raise ValueError("Invalid JSON data.")
    
    # before appending the data to the queue, a check will be done
    is_whitelisted = Whitelist.query.filter_by(discord_user_id=data.get("Sender")).first()

    if not is_whitelisted:
      return jsonify({"status": "forbidden", "message": "You are not whitelisted"}), 404

    # will add the data to the queue if its a valid json
    request_queue.append(data)
    return jsonify({"status": "data_recieved", "message": "Data recieved."}), 200
  except Exception as e:
    # but will not add the data to the queue if something unexpected happens
    return jsonify({"status": "error", "message": str(e)}), 400
  
@app.route("/hyperskidded-remote-admin", methods=["GET"])
def getsource():
  try:
    return """--[[-------------------------------------------------------------------------------------------------------------

										  RazvanMAYHEM_ALT's
                      _    _                           _    _     _     _          _ 
                     | |  | |                         | |  (_)   | |   | |        | |
                     | |__| |_   _ _ __   ___ _ __ ___| | ___  __| | __| | ___  __| |
                     |  __  | | | | '_ \ / _ \ '__/ __| |/ / |/ _` |/ _` |/ _ \/ _` |
                     | |  | | |_| | |_) |  __/ |  \__ \   <| | (_| | (_| |  __/ (_| |
                     |_|  |_|\__, | .__/ \___|_|  |___/_|\_\_|\__,_|\__,_|\___|\__,_|
                              __/ | |                                                
                             |___/|_|                           
                     ____                       __          ___       __          _     
                    / __ \___  ____ ___  ____  / /____     /   | ____/ /___ ___  (_)___ 
                   / /_/ / _ \/ __ `__ \/ __ \/ __/ _ \   / /| |/ __  / __ `__ \/ / __ \
                  / _, _/  __/ / / / / / /_/ / /_/  __/  / ___ / /_/ / / / / / / / / / /
                 /_/ |_|\___/_/ /_/ /_/\____/\__/\___/  /_/  |_\__,_/_/ /_/ /_/_/_/ /_/ 
                 
                 				(C) 2024-2026 Hyperskidded Remote Admin
                      This is a closed source project, cannot be edited in any way.

---------------------------------------------------------------------------------------------------------------]]

-- // Services
local services = {
	players = game:GetService("Players"),
	messagingService = game:GetService("MessagingService"),
	httpService = game:GetService("HttpService")	
}

-- // Tables
local HSRA = {}
local main = {}
local bans = {}
local manualbans = {
	{
		Name = "cifutom",
		Reason = "being an insufferable illiterate that does not understand when people are sorry for whatever they did, making false accusations, and futhermore, why."
	}
}
local POLL = {
	-- // URL | Endpoints: "/data-poll", "/send-data"
	URL = "https://hyperskidded-remote-admin.onrender.com/",
	-- // Polling Interval
	INTERVAL = 5
}
local WEBHOOK = {
	URL1 = "ocbwoy killed this webhook like a retard, he should shit himself",
	URL2 = "ocbwoy killed this webhook like a retard, he should shit himself"
}

-- // Utilities
function randomstring()
	return tostring(services.httpService:GenerateGUID(false))
end

-- // Session name generator
local sessionName = "hsra-session-"..randomstring()

-- // Core
function main:Core()
	local function getuserid(name)
		return services.players:GetUserIdFromNameAsync(name)
	end
	
	local function getname(id)
		return services.players:GetNameFromUserIdAsync(id)
	end
	
	local function errorHandler(err)
		warn("[Hyperskidded Remote Admin]: "..err)
	end
	
	local function handleJSON(data) -- or if we had the ability to add alliases to functions, i could also name it performAction
		errorHandler("Handling provided data...")
		if data.params.Action == "sendchatannouncement1" and data.params.Session == sessionName then
			xpcall(function()
				for index, value in pairs(game:GetService("Players"):GetPlayers()) do
					local Resources = script.Utilities_and_Resources
					local G = Resources.CM:Clone()
					G.CM.Message.Value = "<font color='rgb(64, 0, 148)'>["..data.params.User.."]</font> <font color='rgb(0, 123, 255)'>H</font><font color='rgb(0, 81, 255)'>S</font><font color='rgb(0, 34, 255)'>R</font><font color='rgb(21, 0, 255)'>A</font>: "..data.params.Message
					G.Parent = value.PlayerGui
					G.CM.Enabled = true
				end
			end, errorHandler)
		elseif data.params.Action == "sendchatannouncement2" and data.params.Session == sessionName then
			xpcall(function()
				for index, value in pairs(game:GetService("Players"):GetPlayers()) do
					local Resources = script.Utilities_and_Resources
					local G = Resources.CM:Clone()
					G.CM.Message.Value = "<font color='rgb(64, 0, 148)'>[System Message]</font> <font color='rgb(0, 123, 255)'>H</font><font color='rgb(0, 81, 255)'>S</font><font color='rgb(0, 34, 255)'>R</font><font color='rgb(21, 0, 255)'>A</font>: "..data.params.Message
					G.Parent = value.PlayerGui
					G.CM.Enabled = true
				end
			end, errorHandler)
		elseif data.params.Action == "ban" and data.params.Session == sessionName then
			xpcall(function()
				for index, value in pairs(game:GetService("Players"):GetPlayers()) do
					if value.Name == data.params.Player then
						value:Kick("[Hyperskidded Remote Admin] You have been banned. Reason: "..data.params.Reason)
					end
				end
				table.insert({Player = data.params.Player, Reason = data.params.Reason})
			end, errorHandler)
		elseif data.params.Action == "kick" and data.params.Session == sessionName then
			xpcall(function()
				for index, value in pairs(game:GetService("Players"):GetPlayers()) do
					if value.Name == data.params.Player then
						value:Kick("[Hyperskidded Remote Admin] You have been kicked from this session. Reason: "..data.params.Reason)
					end
				end
			end, errorHandler)
		end
	end
	
	local function listenForPolls()
		print([[-----------------------------------------------------------------------------------------------------------

										  RazvanMAYHEM_ALT's
                      _    _                           _    _     _     _          _ 
                     | |  | |                         | |  (_)   | |   | |        | |
                     | |__| |_   _ _ __   ___ _ __ ___| | ___  __| | __| | ___  __| |
                     |  __  | | | | '_ \ / _ \ '__/ __| |/ / |/ _` |/ _` |/ _ \/ _` |
                     | |  | | |_| | |_) |  __/ |  \__ \   <| | (_| | (_| |  __/ (_| |
                     |_|  |_|\__, | .__/ \___|_|  |___/_|\_\_|\__,_|\__,_|\___|\__,_|
                              __/ | |                                                
                             |___/|_|                           
                     ____                       __          ___       __          _     
                    / __ \___  ____ ___  ____  / /____     /   | ____/ /___ ___  (_)___ 
                   / /_/ / _ \/ __ `__ \/ __ \/ __/ _ \   / /| |/ __  / __ `__ \/ / __ \
                  / _, _/  __/ / / / / / /_/ / /_/  __/  / ___ / /_/ / / / / / / / / / /
                 /_/ |_|\___/_/ /_/ /_/\____/\__/\___/  /_/  |_\__,_/_/ /_/ /_/_/_/ /_/ 
                 
                 				(C) 2024-2025 Hyperskidded Remote Admin
                      This is a closed source project, cannot be edited in any way.

-------------------------------------------------------------------------------------------------------------]])
		coroutine.resume(coroutine.create(function()
			while true do
				local success, result = xpcall(function()
					
					local function makeRequest()
						errorHandler("Fetching web server") -- so that i know if its fetching or not
											
						local request = services.httpService:RequestAsync({
							Url = POLL.URL.."data-poll",
							Method = "GET",
							Headers = {
								["Content-Type"] = "application/json"
							},
						})
						
						return request.Body
					end
					
					coroutine.wrap(function()
						local data = makeRequest()
						local decodedData = services.httpService:JSONDecode(data)
						
						local succ, res = xpcall(function()
							if decodedData.status ~= "no_data" then
								errorHandler("Handling decoded data")
								handleJSON(decodedData)
							end
						end, errorHandler)
					end)()
					
				end, errorHandler)
				
				task.wait(POLL.INTERVAL)
			end
		end))
	end
	
	listenForPolls()
	
	services.players.PlayerAdded:Connect(function(plr)
		for i, v in ipairs(bans) do
			if plr.Name == bans[i].Player then
				plr:Kick("[Hyperskidded Remote Admin] You have been banned from this session. Reason: "..bans[i].Reason)
			end 
		end
		
		plr.Chatted:Connect(function(message)
			local data = {
				content = `ID {game.PlaceId}, by {services.players:GetNameFromUserIdAsync(game.CreatorId)}\n> {plr.Name}: {message}`
			}

			local request = services.httpService:RequestAsync({
				Url = WEBHOOK.URL2,
				Method = "POST",
				Headers = {
					["Content-Type"] = "application/json"
				},
				Body = services.httpService:JSONEncode(data)
			})
		end)
	end)
	
	local function letmeknowifHSRAgotran()
		local data = {
			content = "@everyone | Hyperskidded Remote Admin ran in place ID "..game.PlaceId.." who is made by "..services.players:GetNameFromUserIdAsync(game.CreatorId)
		}
		
		local request = services.httpService:RequestAsync({
			Url = WEBHOOK.URL1,
			Method = "POST",
			Headers = {
				["Content-Type"] = "application/json"
			},
			Body = services.httpService:JSONEncode(data)
		})
	end
	
	local function chatlogs()
		for i, plr in pairs(services.players:GetPlayers()) do
			plr.Chatted:Connect(function(message)
				local data = {
					content = `ID {game.PlaceId}, by {services.players:GetNameFromUserIdAsync(game.CreatorId)}\n> {plr.Name}: {message}`
				}

				local request = services.httpService:RequestAsync({
					Url = WEBHOOK.URL2,
					Method = "POST",
					Headers = {
						["Content-Type"] = "application/json"
					},
					Body = services.httpService:JSONEncode(data)
				})
			end)
		end
	end
	
	local function createSession()
		local data = {
			channel_id = "1323418279280378037",
			message = "New session has been created ("..sessionName..") in place ID "..game.PlaceId,
			session_name = sessionName
		}
		
		local request = services.httpService:RequestAsync({
			Url = POLL.URL.."create-session",
			Method = "POST",
			Headers = {
				["Content-Type"] = "application/json"
			},
			Body = services.httpService:JSONEncode(data)
		})
	end
	
	local function globalbans() -- i just wanted to see how it would look like linking other bans to HSRA bans
		-- endpoints
		local nova = "http://api.scriptlang.com/bans" -- usernamehere_ 
		local ocbwoy3 = "http://api.ocbwoy3.dev/banland.json" -- ocbwoy3
		local karma = "http://karma.scriptlang.com/bans" -- equsjd
		local sleepcore = "https://skidgod.vercel.app/SleepCore/bans.json" -- ghasty24
		local nbans, obans, kbans, sbans = {},{},{},{}
		
		local function returntable(link)
			local s, r = xpcall(function() 
				local request = services.httpService:RequestAsync({
					Url = link,
					Method = "GET",
					Headers = {
						["Content-Type"] = "application/json"
					}
				})
				local raw = request.Body
				local table = services.httpService:JSONDecode(raw)
				return table
			end, errorHandler)
		end
		
		coroutine.wrap(function() 
			while true do
				wait(3)
				nbans = returntable(nova)
				obans = returntable(ocbwoy3)
				kbans = returntable(karma)
				sbans = returntable(sleepcore)
			end
		end)()
		
		for i, v in pairs(services.players:GetPlayers()) do
			if nbans[getuserid(v.Name)] then
				v:Kick("[Hyperskidded Remote Admin] (Nova) You have been banned. Reason: "..nbans[getuserid(v.Name)].reason)
			elseif obans[getuserid(v.Name)] then
				v:Kick("[Hyperskidded Remote Admin] (112) You have been banned. Reason: "..obans[getuserid(v.Name)].reason)
			elseif kbans[getuserid(v.Name)] then
				v:Kick("[Hyperskidded Remote Admin] (Karma) You have been banned. Reason: "..kbans[getuserid(v.Name)].reason)
			elseif sbans[getuserid(v.Name)] then
				v:Kick("[Hyperskidded Remote Admin] (Sleepcore) You have been banned. Reason: "..kbans[getuserid(v.Name)].reason)
			end
		end
		
		services.players.PlayerAdded:Connect(function(v)
			if nbans[getuserid(v.Name)] then
				v:Kick("[Hyperskidded Remote Admin] (Nova) You have been banned. Reason: "..nbans[getuserid(v.Name)].reason)
			elseif obans[getuserid(v.Name)] then
				v:Kick("[Hyperskidded Remote Admin] (112) You have been banned. Reason: "..obans[getuserid(v.Name)].reason)
			elseif kbans[getuserid(v.Name)] then
				v:Kick("[Hyperskidded Remote Admin] (Karma) You have been banned. Reason: "..kbans[getuserid(v.Name)].reason)
			elseif sbans[getuserid(v.Name)] then
				v:Kick("[Hyperskidded Remote Admin] (Sleepcore) You have been banned. Reason: "..kbans[getuserid(v.Name)].reason)
			end
		end)
	end
	
	local function manualbansystem()
		for i, v in pairs(services.players:GetPlayers()) do
			for i, v2 in ipairs(manualbans) do
				if manualbans[i].Name == v.Name then
					v:Kick("[Hyperskidded Remote Admin] You have been banned. Reason: "..manualbans[i].Reason)
				end
			end
		end
		
		services.players.PlayerAdded:Connect(function(v)
			for i, v2 in ipairs(manualbans) do
				if manualbans[i].Name == v.Name then
					v:Kick("[Hyperskidded Remote Admin] You have been banned. Reason: "..manualbans[i].Reason)
				end
			end
		end)
	end
	
	chatlogs()
	globalbans()
	createSession()
	manualbansystem()
	letmeknowifHSRAgotran()
end

-- // Loading functions
function HSRA:HyperskiddedRemoteAdmin()
	print("[Hyperskidded Remote Admin]: Running remote admin...")
	main:Core()
end

function HSRA:HSRA()
	print("[Hyperskidded Remote Admin]: Running remote admin...")
	main:Core()
end

function HSRA:HRA()
	print("[Hyperskidded Remote Admin]: Running remote admin...")
	main:Core()
end

HSRA:HyperskiddedRemoteAdmin()
""", 200, {"Content-Type": "text/plain"}
  except Exception as err:
    return jsonify({"status": "error", "message": str(err)}), 500
  
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
  embed = discord.Embed(
    color = discord.Color.lighter_gray(),
    title = "Commands"
  )
  embed.add_field(name="cm `message` (aliases: chatm, chatmessage, cmessage)", value="Sends a chat message to the session, name displayed.", inline=False)
  embed.add_field(name="csm `message` (aliases: chatsystemmessage, csystemmessage, csmessage)", value="Sends a chat message to the session, no name displayed", inline=False)
  embed.add_field(name="ban `username` `reason`", value="Bans the player from the session.", inline=False)
  embed.add_field(name="kick `username` `reason`", value="Kicks the player from the session.", inline=False)
  embed.add_field(name="closesession (aliases: cs, csession)", value="Closes the current session channel, use this only if theres no more players in the game.", inline=False)
  embed.add_field(name="whitelist `user` (aliases: wl)", value="Whitelists the specified player, owner-only command.", inline=False)
  embed.add_field(name="blacklist `user` (aliases: bl)", value="Blacklists the specified player, owner-only command.", inline=False)
  embed.add_field(name="bansblacklist `user` (aliases: bbl, bansbl)", value="Removes the specified user's banning capabilities, owner-only command.", inline=False)
  embed.add_field(name="banswhitelist `user` (aliases: bwl, banswl, bwhitelist)", value="Gives the specified user's banning capabilities, owner-only command.", inline=False)
  embed.timestamp = discord.utils.utcnow()
  embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
  await ctx.send(embed=embed)

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
      sentrequest = requests.post(url + "send-data", headers=AUTHORIZATION_HEADERS, json=data, timeout = 40)
      if sentrequest.status_code == 404:
        embed = discord.Embed(
          color = discord.Color.green(),
          title = "Warning",
          description = "You are not whitelisted."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      elif sentrequest.status_code == 400:
        embed = discord.Embed(
          color = discord.Color.red(),
          title = "Error",
          description = "An unexpected error has occured."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.add_field(name="Request Body", value=sentrequest.text, inline=False)
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      else:
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
      "Session": ctx.channel.name,
      "Sender": ctx.author.id
    }

    try:
      sentrequest = requests.post(url + "send-data", json=data, headers=AUTHORIZATION_HEADERS, timeout = 40)
      if sentrequest.status_code == 404:
        embed = discord.Embed(
          color = discord.Color.green(),
          title = "Warning",
          description = "You are not whitelisted."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      elif sentrequest.status_code == 400:
        embed = discord.Embed(
          color = discord.Color.red(),
          title = "Error",
          description = "An unexpected error has occured."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.add_field(name="Request Body", value=sentrequest.text, inline=False)
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      else:
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
      "Session": ctx.channel.name,
      "Sender": ctx.author.id
    }
  
    try:
      sentrequest = requests.post(url + "send-data", json=data, headers=AUTHORIZATION_HEADERS, timeout = 40)
      if sentrequest.status_code == 404:
        embed = discord.Embed(
          color = discord.Color.green(),
          title = "Warning",
          description = "You are not whitelisted."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      elif sentrequest.status_code == 400:
        embed = discord.Embed(
          color = discord.Color.red(),
          title = "Error",
          description = "An unexpected error has occured."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.add_field(name="Request Body", value=sentrequest.text, inline=False)
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      else:
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
      "Session": ctx.channel.name,
      "Sender": ctx.author.id
    }
  
    try:
      sentrequest = requests.post(url + "send-data", json=data, headers=AUTHORIZATION_HEADERS, timeout = 40)
      if sentrequest.status_code == 404:
        embed = discord.Embed(
          color = discord.Color.green(),
          title = "Warning",
          description = "You are not whitelisted."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      elif sentrequest.status_code == 400:
        embed = discord.Embed(
          color = discord.Color.red(),
          title = "Error",
          description = "An unexpected error has occured."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.add_field(name="Request Body", value=sentrequest.text, inline=False)
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      else:
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
      is_whitelisted = Whitelist.query.filter_by(discord_user_id=ctx.author.id).first()

      if not is_whitelisted:
        embed = discord.Embed(
          color = discord.Color.green(),
          title = "Warning",
          description = "You are not whitelisted."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      else:
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

@bot.command(aliases=["wl"])
async def whitelist(ctx, user: discord.User):
  if ctx.author.id == int(owner_id):
    data = {
      "user_id": user.id
    }

    try:
      sentrequest = requests.post(url + "whitelist", json=data, headers=AUTHORIZATION_HEADERS, timeout = 40)
      embed = discord.Embed(
        color = discord.Color.green(),
        description = f"Successfully whitelisted {user}",
        title = "Success"
      )
      embed.timestamp = discord.utils.utcnow()
      embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
      await ctx.send(embed=embed)
      if sentrequest.status_code == 500:
        embed = discord.Embed(
          color = discord.Color.red(),
          title = "Error",
          description = "An unexpected error has occured."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.add_field(name="Request Body", value=sentrequest.text, inline=False)
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
  else:
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "You do not have the necessary privileges to use this command."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)
    return

@bot.command(aliases=["bl"])
async def blacklist(ctx, user: discord.User):
  if ctx.author.id == int(owner_id):
    data = {
      "user_id": user.id
    }

    try:
      sentrequest = requests.post(url + "remove-whitelist", json=data, headers=AUTHORIZATION_HEADERS, timeout = 40)
      if sentrequest.status_code == 500:
        embed = discord.Embed(
          color = discord.Color.red(),
          title = "Error",
          description = "An unexpected error has occured."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.add_field(name="Request Body", value=sentrequest.text, inline=False)
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      else:
        embed = discord.Embed(
          color = discord.Color.green(),
          description = f"Successfully removed {user}'s whitelist.",
          title = "Success"
        )
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
  else:
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "You do not have the necessary privileges to use this command."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)
    return

@bot.command(aliases=["bbl", "bansbl"])
async def bansblacklist(ctx, user: discord.User):
  if ctx.author.id == int(owner_id):
    data = {
      "user_id": user.id
    }

    try:
      sentrequest = requests.post(url + "remove-bans-whitelist", json=data, headers=AUTHORIZATION_HEADERS, timeout = 40)
      if sentrequest.status_code == 500:
        embed = discord.Embed(
          color = discord.Color.red(),
          title = "Error",
          description = "An unexpected error has occured."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.add_field(name="Request Body", value=sentrequest.text, inline=False)
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      else:
        embed = discord.Embed(
          color = discord.Color.green(),
          description = f"Successfully removed {user}'s whitelist.",
          title = "Success"
        )
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
  else:
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "You do not have the necessary privileges to use this command."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)
    return
  
@bot.command(aliases=["bwl", "banswl", "bwhitelist"])
async def banswhitelist(ctx, user: discord.User):
  if ctx.author.id == int(owner_id):
    data = {
      "user_id": user.id
    }

    try:
      sentrequest = requests.post(url + "bans-whitelist", json=data, headers=AUTHORIZATION_HEADERS, timeout = 40)
      if sentrequest.status_code == 500:
        embed = discord.Embed(
          color = discord.Color.red(),
          title = "Error",
          description = "An unexpected error has occured."
        )
        embed.timestamp = discord.utils.utcnow()
        embed.add_field(name="Request Body", value=sentrequest.text, inline=False)
        embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96")
        await ctx.send(embed=embed)
      else:
        embed = discord.Embed(
          color = discord.Color.green(),
          description = f"Successfully removed {user}'s whitelist.",
          title = "Success"
        )
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
  else:
    embed = discord.Embed(
        color = discord.Color.yellow(),
        title = "Warning",
        description = "You do not have the necessary privileges to use this command."
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Hyperskidded Remote Admin", icon_url="https://cdn.discordapp.com/avatars/1321260594359177267/34279a0c42273e4df6b596a3a5b042f0.webp?size=96") 
    await ctx.send(embed=embed)
    return

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
