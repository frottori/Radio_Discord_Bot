import requests
import re
import asyncio
import discord

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
async def update_activity(status, bot):
    """Update the bot's Discord activity status"""
    if status:
        # Set activity as Listening
        activity = discord.Activity(type=discord.ActivityType.listening, name=status)
        await bot.change_presence(status=discord.Status.online, activity=activity)
    else:
        # Clear activity
        await bot.change_presence(status=discord.Status.online, activity=None)

#^ other helpers
def get_title_from_api(songs_url):
    """Fetch the current song title from API"""
    """This will depend on the actual API structure -> adjust as needed"""
    response = requests.get(songs_url)
    response.raise_for_status()    
    data = response.json()
    icestats = data.get("icestats", {})
    title = None
    
    for key, value in icestats.items():
        if isinstance(value, dict) and "title" in value:
            title = value["title"]
            break
    return title.title() if title else None

async def get_song_details(title, spotify):
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