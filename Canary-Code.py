import discord
from discord.ext import commands
import logging
import os
import asyncio
import json  # For saving and loading settings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Bot setup with explicit Message Content Intent
intents = discord.Intents.default()
intents.message_content = True  # Explicitly enable message content intent
bot = commands.Bot(command_prefix="/", intents=intents)

# File to store settings
SETTINGS_FILE = "settings.json"

# Dictionaries to store mappings and states
group_mappings = {}      # {group_id: {guild_id: channel}}
relay_enabled = {}       # {group_id: {guild_id: relay_status}}
server_groups = {}       # {guild_id: group_id} - Tracks each server's group

# Functions for saving and loading settings
def load_settings():
    """Loads settings from a JSON file."""
    global group_mappings, relay_enabled, server_groups
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
            group_mappings = {k: {int(gid): bot.get_channel(cid) for gid, cid in v.items()} for k, v in data["group_mappings"].items()}
            relay_enabled = {k: {int(gid): status for gid, status in v.items()} for k, v in data["relay_enabled"].items()}
            server_groups = {int(gid): group_id for gid, group_id in data["server_groups"].items()}
        print("Settings loaded successfully.")
    except FileNotFoundError:
        print("Settings file not found. Starting with empty settings.")
    except Exception as e:
        print(f"Error loading settings: {e}")

def save_settings():
    """Saves settings to a JSON file."""
    data = {
        "group_mappings": {k: {gid: channel.id for gid, channel in v.items()} for k, v in group_mappings.items()},
        "relay_enabled": {k: {gid: status for gid, status in v.items()} for k, v in relay_enabled.items()},
        "server_groups": server_groups
    }
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)
    print("Settings saved successfully.")

@bot.event
async def on_ready():
    load_settings()  # Load settings on startup
    print(f'{bot.user} is connected and ready.')

@bot.command(name="setgroup")
@commands.has_permissions(administrator=True)
async def set_group(ctx, group_id: str):
    """Sets the group ID for this server, linking it with other servers in the same group."""
    server_groups[ctx.guild.id] = group_id
    save_settings()  # Save settings after updating
    await ctx.send(f"Group ID set to '{group_id}' for this server. Use `/setsharedchannel` to configure a shared channel for this group.")

@bot.command(name="setsharedchannel")
@commands.has_permissions(administrator=True)
async def set_shared_channel(ctx, channel: discord.TextChannel):
    """Sets the announcement channel for message relaying within the server's group using a channel mention."""
    # Ensure the server has a group set
    group_id = server_groups.get(ctx.guild.id)
    if not group_id:
        await ctx.send("Please set a group ID for this server first using `/setgroup <group_id>`.")
        return

    # Set up the shared channel for this server in the specified group
    if group_id not in group_mappings:
        group_mappings[group_id] = {}
        relay_enabled[group_id] = {}

    group_mappings[group_id][ctx.guild.id] = channel
    relay_enabled[group_id][ctx.guild.id] = True
    save_settings()  # Save settings after updating
    await ctx.send(f"Shared channel set to {channel.mention} for group '{group_id}' in this server.")

@bot.command(name="enable")
@commands.has_permissions(administrator=True)
async def enable_relay(ctx):
    """Enables message relaying in the designated channel within the server's group."""
    group_id = server_groups.get(ctx.guild.id)
    if group_id and group_id in relay_enabled and ctx.guild.id in relay_enabled[group_id]:
        relay_enabled[group_id][ctx.guild.id] = True
        save_settings()  # Save settings after updating
        await ctx.send(f"Message relaying has been enabled for group '{group_id}'.")
    else:
        await ctx.send("This server is not set up in a group or shared channel. Use `/setgroup` and `/setsharedchannel` to configure it first.")

@bot.command(name="disable")
@commands.has_permissions(administrator=True)
async def disable_relay(ctx):
    """Disables message relaying in the designated channel within the server's group."""
    group_id = server_groups.get(ctx.guild.id)
    if group_id and group_id in relay_enabled and ctx.guild.id in relay_enabled[group_id]:
        relay_enabled[group_id][ctx.guild.id] = False
        save_settings()  # Save settings after updating
        await ctx.send(f"Message relaying has been disabled for group '{group_id}'.")
    else:
        await ctx.send("This server is not set up in a group or shared channel. Use `/setgroup` and `/setsharedchannel` to configure it first.")

@bot.command(name="status")
@commands.has_permissions(administrator=True)
async def status(ctx):
    """Displays the current relay status and shared channel for this server within the group."""
    group_id = server_groups.get(ctx.guild.id)
    if group_id and group_id in group_mappings and ctx.guild.id in group_mappings[group_id]:
        shared_channel = group_mappings[group_id][ctx.guild.id]
        status = "enabled" if relay_enabled[group_id].get(ctx.guild.id, False) else "disabled"
        await ctx.send(f"Relaying is currently {status}. Shared channel for group '{group_id}' is {shared_channel.mention}.")
    else:
        await ctx.send("No shared channel is set for this server in the specified group.")

@bot.command(name="ping")
async def ping(ctx):
    """A simple test command to verify the bot is working."""
    await ctx.send("Pong!")

@bot.command(name="display")
@commands.has_permissions(administrator=True)
async def display(ctx):
    """Displays all connected channels within the server's group and their relay status."""
    group_id = server_groups.get(ctx.guild.id)
    if not group_id or group_id not in group_mappings or not group_mappings[group_id]:
        await ctx.send(f"No channels are currently connected for message relaying in the group for this server.")
        return

    display_message = f"**Connected Channels for Group '{group_id}':**\n\n"
    for guild_id, channel in group_mappings[group_id].items():
        relay_status = "enabled" if relay_enabled[group_id].get(guild_id, False) else "disabled"
        display_message += f"- **Server**: {channel.guild.name} | **Channel**: {channel.mention} | **Status**: {relay_status}\n"

    await ctx.send(display_message)

async def relay_message(target_channel, content):
    """Helper function to relay messages with rate limiting."""
    try:
        await target_channel.send(content)
        await asyncio.sleep(1)  # Rate limiting delay (adjust as needed)
    except discord.HTTPException as e:
        logging.error(f"Failed to relay message: {e}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return  # Ignore bot's own messages

    await bot.process_commands(message)  # Process commands before any other on_message logic

    # Relay messages within the server's group
    group_id = server_groups.get(message.guild.id)
    if group_id and group_id in group_mappings and message.guild.id in group_mappings[group_id]:
        origin_channel = group_mappings[group_id][message.guild.id]
        if relay_enabled[group_id].get(message.guild.id, False) and message.channel.id == origin_channel.id:
            # Format the message content with target server-specific mentions
            def format_mentions(content, target_guild):
                """Replaces user mentions with their server-specific nickname."""
                formatted_content = content
                for user in message.mentions:
                    # Attempt to get the user in the target guild
                    member = target_guild.get_member(user.id)
                    if member:
                        # Replace mention with nickname in the target guild if available
                        formatted_content = formatted_content.replace(
                            f"<@{user.id}>", f"@{member.display_name}"
                        )
                return formatted_content

            # Relay the message to other servers' designated channels within the same group
            relay_tasks = [
                relay_message(
                    target_channel,
                    f"[{message.guild.name}] {message.author.display_name}: {format_mentions(message.content, target_channel.guild)}"
                )
                for target_guild_id, target_channel in group_mappings[group_id].items()
                if target_guild_id != message.guild.id and relay_enabled[group_id].get(target_guild_id, False)
            ]
            await asyncio.gather(*relay_tasks)

# Retrieve the bot token from environment variables
token = os.getenv("DISCORD_TOKEN")
if not token:
    raise ValueError("DISCORD_TOKEN environment variable is not set.")
bot.run(token)
