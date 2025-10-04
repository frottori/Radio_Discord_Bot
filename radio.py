import discord
from discord.ext import commands, tasks
from discord.utils import get
from discord import app_commands
import requests
import json
from datetime import datetime
from collections import deque
import re
import pytz
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import asyncio
import os
from dotenv import load_dotenv

#^ Bot setup
intents = discord.Intents.default()
intents.message_content = True  
bot = commands.Bot(command_prefix="/", intents=intents)
radio_playing = False
greece_tz = pytz.timezone('Europe/Athens')
# Store last played songs locally
song_history = deque(maxlen=50) # Keep only last 50 songs

# Load environment variables from a .env file if present
load_dotenv()

#^ Radio and API URLs
RADIO_URL = os.environ.get("RADIO_URL")
SONGS_URL = os.environ.get("SONGS_URL")
KEYWORD = os.environ.get("KEYWORD")
#^ Spotify API credentials
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")

if not RADIO_URL:
    raise RuntimeError("RADIO_URL environment variable not set. Set RADIO_URL to your stream URL (e.g. http://.../stream).")
if not SONGS_URL:
    print("Warning: SONGS_URL not configured. NowPlaying/History may not work.")
if not KEYWORD:
    print("Warning: KEYWORD not configured. Commercial break detection may not work.")

#^ Initialize Spotify client
try:
    if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        ))
    else:
        spotify = None
        print("Warning: Spotify API credentials not configured in environment variables")
except:
    spotify = None
    print("Warning: Spotify API not configured")

#^ Ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    # Sync slash commands (global). For development use guild=discord.Object(id=GUILD_ID)
    try:
        await bot.tree.sync()
        print("Slash commands synced")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    # Start the background task
    update_song_history.start()  

#* Background task to update song history
@tasks.loop(minutes=1)  # Check every 1 minutes
async def update_song_history():
    global radio_playing
    # Only run if radio is currently playing
    if not radio_playing:
        return
        
    try:
        title = get_title_from_api(SONGS_URL)
        if title:
            timestamp = datetime.now(greece_tz).strftime("%H:%M") 
            # Only add if it's different from the last song
            if not song_history or song_history[-1]['title'] != title:    
                if get_title_normalized(title) != KEYWORD.lower():
                    await update_activity(f"{title}", bot)
                    song_history.append({
                        'title': title,
                        'time': timestamp
                    })
    except:
        pass 

#* Import helper functions
from helpers import (
    populate_np_embed,
    populate_lp_embed,
    get_title_from_api,
    get_song_details,
    get_title_normalized,
    update_activity
)

#& Slash Commands
#? radio
@bot.tree.command(name="radio", description="Join your voice channel and stream radio!")
async def radio(interaction: discord.Interaction):
    await interaction.response.defer()
    global radio_playing
    radio_playing = True

    user = interaction.user
    if not getattr(user, "voice", None):
        await interaction.followup.send("You must be in a voice channel to use /radio", ephemeral=True)
        return

    channel = user.voice.channel
    voice = get(bot.voice_clients, guild=interaction.guild)

    try:
        if voice and voice.is_connected():
            if voice.channel != channel:
                await voice.move_to(channel)
        else:
            voice = await channel.connect()
    except discord.Forbidden:
        await interaction.followup.send("Missing permissions to connect/speak in your channel.", ephemeral=True)
        return

    if not voice.is_playing():
        voice.play(discord.FFmpegPCMAudio(RADIO_URL))
        await update_activity("Radio!", bot)
    await interaction.followup.send("🎶 Now streaming Radio!", ephemeral=True)

#?pause
@bot.tree.command(name="pause", description="Pause the radio stream")
async def pause(interaction: discord.Interaction):
    await interaction.response.defer()
    voice = get(bot.voice_clients, guild=interaction.guild)
    if voice and voice.is_playing():
        voice.pause()
        await interaction.followup.send("Paused.", ephemeral=True)
    else:
        await interaction.followup.send("Nothing is playing right now...", ephemeral=True)

#?resume
@bot.tree.command(name="resume", description="Resume the radio stream")
async def resume(interaction: discord.Interaction):
    await interaction.response.defer()
    voice = get(bot.voice_clients, guild=interaction.guild)
    if voice and voice.is_paused():
        voice.resume()
        await interaction.followup.send("Resumed", ephemeral=True)
    else:
        await interaction.followup.send("Nothing is paused...", ephemeral=True)

#?stop
@bot.tree.command(name="stop", description="Stop playing and disconnect")
async def stop(interaction: discord.Interaction):
    await interaction.response.defer()
    global radio_playing
    voice = get(bot.voice_clients, guild=interaction.guild)
    if voice:
        radio_playing = False
        await voice.disconnect()
        await update_activity(None, bot)
        await interaction.followup.send("Disconnected.", ephemeral=True)
    else:
        await interaction.followup.send("Not connected to a voice channel...", ephemeral=True)

#?nowplaying
@bot.tree.command(name="nowplaying", description="Show currently playing song")
async def nowplaying(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        title = get_title_from_api(SONGS_URL)
        
        # Handle commercial breaks
        if title and get_title_normalized(title) == KEYWORD.lower():
            await interaction.followup.send("Now Playing: **Commercial Break**", ephemeral=True)
            return
        # Handle no song found   
        if not title:
            await interaction.followup.send("Could not find the current song.", ephemeral=True)
            return
        
        # Get detailed song information from Spotify
        song_details = await get_song_details(title, spotify)
        
        if song_details:
            embed = populate_np_embed(song_details)
            await interaction.followup.send(f"Now Playing: **{title}**", embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"Now Playing: **{title}**", ephemeral=True)
            
    except json.JSONDecodeError:
        await interaction.followup.send("Error parsing song info.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send("Error fetching song.", ephemeral=True)

#?lastplayed
@bot.tree.command(name="lastplayed", description="Show 10 last played songs (max 50)")
@app_commands.describe(num="Number of songs to show (1-50)")
async def lastplayed(interaction: discord.Interaction, num: int = 10):
    await interaction.response.defer()
    # sanitize num
    if num < 1:
        num = 1
    elif num > 50:
        num = 50
    
    if not song_history:
        await interaction.followup.send("No previous history available yet", ephemeral=True)
        return
    
    # Get the last 'num' songs
    recent_songs = list(song_history)[-num:]
    recent_songs.reverse()  # Show most recent first
    embed = populate_lp_embed(recent_songs, len(recent_songs))
    
    await interaction.followup.send(embed=embed, ephemeral=True)

#^ Run the bot
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable not set. Create a .env file or set the variable in your environment.")

bot.run(DISCORD_TOKEN)