import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import google.generativeai as genai
import sqlite3

# Load environment variables
load_dotenv()

# Configure the bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=os.getenv("PREFIX"), intents=intents)

# Configure the GeminiAPI
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize the database
def initialize_database():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS channels
                 (server_id INTEGER PRIMARY KEY, channel_id INTEGER)''')
    conn.commit()
    conn.close()

# Database functions
def add_channel(server_id, channel_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO channels (server_id, channel_id) 
                 VALUES (?, ?)''', (server_id, channel_id))
    conn.commit()
    conn.close()

def remove_channel(server_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''DELETE FROM channels WHERE server_id = ?''', (server_id,))
    conn.commit()
    conn.close()

def get_channel(server_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''SELECT channel_id FROM channels WHERE server_id = ?''', (server_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

chat_sessions = {}

initialize_database()

@bot.event
async def on_ready():
    tree = await bot.tree.sync()
    print(f"Logged in as {bot.user}\nServing {len(bot.guilds)} server(s)\nSynced {len(tree)} slash command(s)")
    server_count = len(bot.guilds)
    activity_name = f"{server_count} Server{'s' if server_count > 1 else '!'}"
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=activity_name))

@bot.tree.command(description="Check the current latency of the bot.")
async def ping(interaction: discord.Interaction):
    embed = discord.Embed(color=discord.Color.light_embed(), description=f"Pong! {round(bot.latency * 1000, 2)} ms")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(description="Send a prompt to GeminiAPI")
async def prompt(interaction: discord.Interaction, prompt: str):
    embed = discord.Embed(color=discord.Color.light_embed(), title="Generating...")
    await interaction.response.send_message(embed=embed)
    
    try:
        channel_id = interaction.channel_id
        if channel_id not in chat_sessions:
            chat_sessions[channel_id] = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config=generation_config,
            ).start_chat(history=[])

        chat_session = chat_sessions[channel_id]
        response = chat_session.send_message(f"System:{os.getenv('PRE-PROMPT')}. Prompt:{prompt}")
        response_text = response.text
        
        embed = discord.Embed(color=discord.Color.light_embed(), title="GeminiAPI",
                              description=f"**PROMPT**\n{prompt}\n\n**RESPONSE**\n{response_text}")
        await interaction.edit_original_response(embed=embed)
    
    except Exception as e:
        error_message = f"Failed to generate a response for the prompt: `{prompt}`. Error: {str(e)}"
        embed = discord.Embed(color=discord.Color.red(), title="Error: Failed to generate response",
                              description=error_message)
        await interaction.edit_original_response(embed=embed)

@bot.tree.command(description="Set the channel for the chatbot")
async def setchannel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    embed = discord.Embed(color=discord.Color.light_embed(), description="Setting the channel...")
    await interaction.response.send_message(embed=embed)

    try:
        if not interaction.user.guild_permissions.manage_channels:
            embed.description = "You do not have the permission to use that command."
            await interaction.edit_original_response(embed=embed)
            return
    except:
        embed.description = "You do not have the permission to use that command."
        await interaction.edit_original_response(embed=embed)
        return

    channel = channel or interaction.channel
    channel_id = channel.id
    server_id = interaction.guild.id
    
    current_channel_id = get_channel(server_id)
    
    if current_channel_id is None:
        add_channel(server_id, channel_id)
        embed = discord.Embed(color=discord.Color.light_embed(), description=f"Channel <#{channel_id}> set for the chatbot.")
        await interaction.edit_original_response(embed=embed)
    elif current_channel_id == channel_id:
        embed = discord.Embed(color=discord.Color.light_embed(), description=f"The channel <#{channel_id}> is already set for the chatbot.")
        await interaction.edit_original_response(embed=embed)
    else:
        old_channel = bot.get_channel(current_channel_id)
        remove_channel(server_id)
        add_channel(server_id, channel_id)
        embed = discord.Embed(color=discord.Color.light_embed(),
                              description=f"The old channel was <#{current_channel_id}>. Now set to <#{channel_id}> for the chatbot.")
        await interaction.edit_original_response(embed=embed)

@bot.tree.command(description="Remove the channel set for the chatbot")
async def removechannel(interaction: discord.Interaction):
    embed = discord.Embed(color=discord.Color.light_embed(), description="Removing the channel...")
    await interaction.response.send_message(embed=embed)

    try:
        if not interaction.user.guild_permissions.manage_channels:
            embed.description = "You do not have the permission to use that command."
            await interaction.edit_original_response(embed=embed)
            return
    except:
        embed.description = "You do not have the permission to use that command."
        await interaction.edit_original_response(embed=embed)
        return

    server_id = interaction.guild.id
    current_channel_id = get_channel(server_id)
    
    if current_channel_id is None:
        embed.description = "No channel is currently set for the chatbot."
        await interaction.edit_original_response(embed=embed)
    else:
        remove_channel(server_id)
        embed.description = "Channel removed for the chatbot."
        await interaction.edit_original_response(embed=embed)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.content:
        return

    channel_id = message.channel.id
    server_id = message.guild.id
    set_channel_id = get_channel(server_id)
    
    if set_channel_id is not None and channel_id == set_channel_id:
        try:
            if channel_id not in chat_sessions:
                chat_sessions[channel_id] = genai.GenerativeModel(
                    model_name="gemini-1.5-flash",
                    generation_config=generation_config,
                ).start_chat(history=[])

            chat_session = chat_sessions[channel_id]
            response = chat_session.send_message(f"System:{os.getenv('PRE-PROMPT')}. Prompt:{message.author.display_name} Said: {message.content}")
            response_text = response.text
            
            await message.reply(response_text)
        except Exception as e:
            error_message = f"Failed to generate a response for the prompt: `{message.content}`. Error: {str(e)}"
            await message.reply(error_message)

@bot.tree.command(description="The help command which lists out all the basic information and commands for using the bot")
async def help(interaction: discord.Interaction):
    embed = discord.Embed(color=discord.Color.light_embed(), title="Help")
    embed.add_field(name="LINKS AND URLS", value="[Youtube Tutorial](https://www.youtube.com/)\n[Official Discord Server](https://discord.gg/4uFYtfpnfP)\n[GeminiAPI Documentation](https://ai.google.dev/gemini-api/docs)\n[Discord.py Documentation](https://discordpy.readthedocs.io/en/stable/)")
    embed.add_field(name="HELP COMMANDS", value="**/help**\nShows the list of all commands with useful links and urls.\n**/ping**\nShows the current latency of the bot in ms.\n**/prompt**\nSend a prompt to the AI and get an embedded response, works in any channel.\n**/setchannel**\nSets the channel used for live Ai chat in a server.\n**/removechannel**\nRemoves the channel set for live Ai chat in a server from the database.", inline=False)
    embed.set_footer(text="Still need help? Join our official Discord server at https://discord.gg/4uFYtfpnfP")
    await interaction.response.send_message(embed=embed)

# Run the bot
try:
    bot.run(os.getenv("DISCORD_BOT_TOKEN"))
except Exception as e:
    print(f"An error occurred while starting the bot: {e}")