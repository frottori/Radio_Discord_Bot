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
bot = commands.Bot(command_prefix="!", intents=intents)
radio_playing = False
greece_tz = pytz.timezone('Europe/Athens')
# Store last played songs locally
# Keep only last 50 songs
song_history = deque(maxlen=50) 

# Load environment variables from a .env file if present
load_dotenv()

#^ Radio and API URLs
RADIO_URL = os.environ.get("RADIO_URL")
SONGS_URL = os.environ.get("SONGS_URL")
KEYWORD = os.environ.get("KEYWORD")

if not RADIO_URL:
    raise RuntimeError("RADIO_URL environment variable not set. Set RADIO_URL to your stream URL (e.g. http://.../stream).")
if not SONGS_URL:
    print("Warning: SONGS_URL not configured. NowPlaying/History may not work.")
if not KEYWORD:
    print("Warning: KEYWORD not configured. Commercial break detection may not work.")

#^ Spotify API credentials
# Read Spotify credentials from environment for security
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")

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

#? Background task to update song history
@tasks.loop(minutes=1)  # Check every 1 minutes
async def update_song_history():
    global radio_playing
    # Only run if radio is currently playing
    if not radio_playing:
        return
        
    try:
        title = get_title_from_api()
        if title:
            timestamp = datetime.now(greece_tz).strftime("%H:%M") 
            # Only add if it's different from the last song
            if not song_history or song_history[-1]['title'] != title:    
                if get_title_normalized(title) != KEYWORD.lower():
                    await update_activity(f"{title}")
                    song_history.append({
                        'title': title,
                        'time': timestamp
                    })
    except:
        pass  

#* Ready
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

#$ Slash Commands
#? radio
@bot.tree.command(name="radio", description="Join your voice channel and stream radio")
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
        await update_activity("Radio!")
    await interaction.followup.send("🎶 Now streaming Radio!", ephemeral=True)

#?pause
@bot.tree.command(name="pause")
async def pause(interaction: discord.Interaction):
    await interaction.response.defer()
    voice = get(bot.voice_clients, guild=interaction.guild)
    if voice and voice.is_playing():
        voice.pause()
        await interaction.followup.send("Paused.", ephemeral=True)
    else:
        await interaction.followup.send("Nothing is playing right now...", ephemeral=True)

#?resume
@bot.tree.command(name="resume")
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
        await update_activity(None)
        await interaction.followup.send("Disconnected.", ephemeral=True)
    else:
        await interaction.followup.send("Not connected to a voice channel...", ephemeral=True)

#?nowplaying
@bot.tree.command(name="nowplaying", description="Show currently playing song")
async def nowplaying(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        title = get_title_from_api()
        
        # Handle commercial breaks
        if title and get_title_normalized(title) == KEYWORD.lower():
            await interaction.followup.send("Now Playing: **Commercial Break**", ephemeral=True)
            return
        # Handle no song found   
        if not title:
            await interaction.followup.send("Could not find the current song.", ephemeral=True)
            return
        
        # Get detailed song information from Spotify
        song_details = await get_song_details(title)
        
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

#$ Helper Functions
#^ Populate embeds
def populate_np_embed(song_details):
    """Create a Discord embed for now playing song details"""
    embed = discord.Embed(
        title=f"{song_details['name']}",
        color=0x1DB954  # green
    )
    
    embed.add_field(
        name="Artist(s)",
        value=", ".join(song_details['artists']),
        inline=True
    )
    
    embed.add_field(
        name="Album",
        value=f"{song_details['album']}",
        inline=True
    )
    
    embed.add_field(
        name="Release Date",
        value=f"{song_details['release_date']}",
        inline=True
    )
    
    if song_details['image_url']:
        embed.set_thumbnail(url=song_details['image_url'])
    
    if song_details['spotify_url']:
        embed.add_field(
            name="Listen on Spotify",
            value=f"[Spotify Link]({song_details['spotify_url']})",
            inline=False
        )
    return embed

def populate_lp_embed(songs, count):
    """Create a Discord embed for last played songs"""
    embed = discord.Embed(
        title=f"Last Played - {count} Songs",
        color=0xe4001b
    )
    
    lines = []
    for i, song in enumerate(songs, 1):
        lines.append(f"{i}. **{song['title'].title()}** Played at {song['time']}")
    
    embed.description = "\n".join(lines)
    return embed

#^ Update activity
async def update_activity(status):
    """Update the bot's Discord activity status"""
    if status:
        # Set activity as Listening
        activity = discord.Activity(type=discord.ActivityType.listening, name=status)
        await bot.change_presence(status=discord.Status.online, activity=activity)
    else:
        # Clear activity
        await bot.change_presence(status=discord.Status.online, activity=None)

#^ other helpers
def get_title_from_api():
    """Fetch the current song title from API"""
    """This will depend on the actual API structure -> adjust as needed"""
    response = requests.get(SONGS_URL)
    response.raise_for_status()    
    data = response.json()
    icestats = data.get("icestats", {})
    title = None
    
    for key, value in icestats.items():
        if isinstance(value, dict) and "title" in value:
            title = value["title"]
            break
    return title.title() if title else None

async def get_song_details(title):
    """Fetch detailed song information from Spotify"""
    if not spotify:
        return None
    
    try:
        # Clean up the title for better search results
        clean_title = re.sub(r'[^\w\s-]', '', title)
        
        # Add retry logic for connection issues
        for attempt in range(3):  # Try up to 3 times
            try:
                # Search for the track
                results = spotify.search(q=clean_title, type='track', limit=1)
                break  # Success, exit retry loop
            except Exception as e:
                print(f"Spotify search attempt {attempt + 1} failed: {e}")
                if attempt == 2:  # Last attempt
                    return None
                await asyncio.sleep(2)  # Wait 2 seconds before retry
        
        if results['tracks']['items']:
            track = results['tracks']['items'][0]
            
            # Get album info
            album = track['album']
            artists = [artist['name'] for artist in track['artists']]
            
            return {
                'name': track['name'],
                'artists': artists,
                'album': album['name'],
                'release_date': album['release_date'],
                'image_url': album['images'][0]['url'] if album['images'] else None,
                'spotify_url': track['external_urls']['spotify'],
            }
    except Exception as e:
        print(f"Spotify API error: {e}")
    return None

def get_title_normalized(title):
    """Normalize title for comparison"""
    return re.sub(r"\s+", " ", title).strip().lower()

#^ Run the bot
# Get the Discord token from environment variable DISCORD_TOKEN
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable not set. Create a .env file or set the variable in your environment.")

bot.run(DISCORD_TOKEN)