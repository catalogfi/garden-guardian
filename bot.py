import discord
import subprocess
import socket
import platform
import json
import asyncio
from datetime import datetime, timedelta, timezone
import shlex

bot = discord.Bot()

# Load configuration
with open("config/config.json", "r") as config_file:
    config = json.load(config_file)

# Constants
ALERT_THRESHOLD = 50  # Alert when CPU or RAM usage exceeds 50%
ALERT_CHANNEL_ID = config.get("alert_channel_id", None)
alerted_containers = {}  # Track container alerts
AUDIT_LOG_FILE = "audit_log.json"  # File to store audit logs

async def check_permissions(ctx, required_role="dev"):
    """Check if the user has the required role."""
    user_id = ctx.author.id

    # Load latest roles
    with open("config/config.json", "r") as file:
        config = json.load(file)

    if user_id in config["admins"]:  # Full access for Admins
        return "admin"
    elif required_role == "dev" and user_id in config["devs"]:  # Devs can read
        return "dev"

    await ctx.respond("❌ You do not have permission to use this command.", ephemeral=True)
    return None

def get_current_time():
    local_timezone = timezone(timedelta(hours=config["timezone_offset"]))
    current_time = datetime.now(local_timezone).strftime("%I:%M %p - %d/%m/%Y")
    return current_time

async def get_container_names(ctx: discord.AutocompleteContext):
    try:
        result = subprocess.check_output(['docker', 'ps', '--all', '--format', '{{.Names}}'], text=True)
        container_names = result.strip().split('\n')
        return [name for name in container_names if name] or ["No containers available"]
    except subprocess.CalledProcessError:
        return ["Error retrieving containers"]

def log_command(user_id, username, command, args):
    """Log command execution to a file."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "username": username,
        "command": command,
        "args": args
    }

    try:
        with open(AUDIT_LOG_FILE, "a") as log_file:
            log_file.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Error writing to audit log: {e}")
        
def log_role_change(action, role, user_id, admin_id):
    """Log user role changes."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,  # "add" or "remove"
        "role": role,
        "user_id": user_id,
        "admin_id": admin_id
    }
    try:
        with open("role_audit.json", "a") as log_file:
            log_file.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"⚠️ Error logging role change: {e}")


@bot.event
async def on_connect():
    try:
        await bot.sync_commands()
    except discord.errors.Forbidden as e:
        print("\n⚠️  Warning: Could not sync commands - Missing permissions")
        print("\nTo fix this, please:")
        print("1. Remove the bot from your server")
        print(f"2. Reinvite using this link: https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=2147483648&scope=bot%20applications.commands")
        print("\nThe bot will continue to run, but slash commands may not work properly until this is fixed.\n")
    except Exception as e:
        print(f"\n⚠️  Error syncing commands: {e}\n")

@bot.event
async def on_ready():
    # Change bot username (limited to twice per hour)
    desired_name = config["bot_name"]

    if bot.user.name != desired_name:
        try:
            await bot.user.edit(username=desired_name)
            print(f"✅ Changed bot name to {desired_name}")
        except discord.errors.HTTPException:
            print("❌ Rate limit reached! Can't change username right now.")

    # Change bot avatar
    with open("avatar.png", "rb") as avatar_file:
        avatar_bytes = avatar_file.read()
        try:
            await bot.user.edit(avatar=avatar_bytes)
            print("✅ Changed bot avatar successfully!")
        except discord.errors.HTTPException:
            print("❌ Rate limit reached! Can't change avatar right now.")

    # Set bot status
    activity_type = config["status"]["type"]
    activity_message = config["status"]["message"]

    if activity_type == "playing":
        activity = discord.Game(name=activity_message)
    elif activity_type == "listening":
        activity = discord.Activity(type=discord.ActivityType.listening, name=activity_message, assets={"large_image": "embedded_background"} )
    elif activity_type == "watching":
        activity = discord.Activity(type=discord.ActivityType.watching, name=activity_message)
    else:
        activity = None

    await bot.change_presence(activity=activity)
    print("✅ Bot is online and monitoring Docker!")
    bot.loop.create_task(alert_monitor())


# Docker Management Commands Group
docker_management = bot.create_group("docker", "Manage Docker containers")

@bot.slash_command(description="Add a user as an Admin or Dev (Admins only).")
async def add(ctx, role: discord.Option(str, choices=["dev", "admin"]), user: discord.Member):
    user_id = user.id

    with open("config/config.json", "r") as file:
        config = json.load(file)

    if ctx.author.id not in config["admins"]:
        await ctx.respond("❌ Only Admins can use this command.")
        return

    if role == "dev" and user_id not in config["devs"]:
        config["devs"].append(user_id)
    elif role == "admin" and user_id not in config["admins"]:
        config["admins"].append(user_id)
    else:
        await ctx.respond(f"✅ `{user.name}` is already a {role}.")
        return

    with open("config/config.json", "w") as file:
        json.dump(config, file, indent=4)

    # Log the role change
    log_role_change("add", role, user_id, ctx.author.id)

    await ctx.respond(f"✅ `{user.name}` has been added as a {role}.")

@bot.slash_command(description="Remove a user from Admin or Dev role (Admins only).")
async def remove(ctx, role: discord.Option(str, choices=["dev", "admin"]), user: discord.Member):
    user_id = user.id

    with open("config/config.json", "r") as file:
        config = json.load(file)

    if ctx.author.id not in config["admins"]:
        await ctx.respond("❌ Only Admins can use this command.")
        return

    if role == "dev" and user_id in config["devs"]:
        config["devs"].remove(user_id)
    elif role == "admin" and user_id in config["admins"]:
        config["admins"].remove(user_id)
    else:
        await ctx.respond(f"⚠️ `{user.name}` is not a {role}.")
        return

    with open("config/config.json", "w") as file:
        json.dump(config, file, indent=4)

    # Log the role change
    log_role_change("remove", role, user_id, ctx.author.id)

    await ctx.respond(f"✅ `{user.name}` has been removed from {role}.")

@docker_management.command(description="Execute Docker container management commands.")
async def execute(ctx, action: discord.Option(str, choices=['start', 'stop', 'restart', 'pause', 'unpause', 'delete']), 
                 container_name: discord.Option(str, autocomplete=discord.utils.basic_autocomplete(get_container_names))):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return
    role = await check_permissions(ctx, "admin")
    if not role:
        return

    log_command(ctx.author.id, ctx.author.name, "execute", {"action": action, "container_name": container_name})

    try:
        await ctx.defer()
        action = shlex.quote(action.lower())
        container_name = shlex.quote(container_name)
        
        response = ""

        if action == "delete":
            container_status = subprocess.check_output(['docker', 'inspect', '-f', '{{.State.Status}}', container_name], text=True).strip()
            if container_status == 'running':
                await ctx.respond(f"Container `{container_name}` is still running. Please stop it before attempting to delete.")
                return
            subprocess.check_output(['docker', 'rm', container_name])
            response = f"Container `{container_name}` has been deleted."
        else:
            subprocess.check_output(['docker', action, container_name])
            response = f"Container `{container_name}` has been {action}ed."

        embed = discord.Embed(
            title="**__Docker Management__**",
            description=response,
            color=discord.Colour.blurple(),
        )
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        await ctx.respond(f"Error executing Docker command: {e}")
        
@bot.slash_command(description="View the role change audit log.")
async def audit_roles(ctx):
    if ctx.author.id not in config["admins"]:
        await ctx.respond("❌ Only Admins can view role change logs.")
        return

    try:
        with open("role_audit.json", "r") as log_file:
            logs = log_file.readlines()
        
        if not logs:
            await ctx.respond("📜 No role changes recorded yet.")
            return

        formatted_logs = [
            f"📌 **{log['action'].capitalize()} {log['role']}** | <@{log['user_id']}> by <@{log['admin_id']}> at `{log['timestamp']}`"
            for log in map(json.loads, logs)
        ]

        await ctx.respond("\n".join(formatted_logs[:10]))  # Show only last 10 logs
    except FileNotFoundError:
        await ctx.respond("📜 No role changes recorded yet.")
    except Exception as e:
        await ctx.respond(f"⚠️ Error reading logs: {e}")

@bot.slash_command(description="View current Admins and Devs.")
async def roles(ctx):
    with open("config/config.json", "r") as file:
        config = json.load(file)

    admins = [f"<@{id}>" for id in config["admins"]]
    devs = [f"<@{id}>" for id in config["devs"]]

    embed = discord.Embed(title="🔹 User Roles", color=discord.Colour.blue())
    embed.add_field(name="👑 Admins", value=", ".join(admins) if admins else "None", inline=False)
    embed.add_field(name="🛠 Devs", value=", ".join(devs) if devs else "None", inline=False)

    await ctx.respond(embed=embed)

@docker_management.command(description="Manage Docker images.")
async def images(ctx, action: discord.Option(str, choices=['list', 'pull', 'remove']), 
                image_name: discord.Option(str) = None):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    log_command(ctx.author.id, ctx.author.name, "images", {"action": action, "image_name": image_name})

    try:
        await ctx.defer()
        response = ""

        if action == "list":
            result = subprocess.check_output(['docker', 'images', '--format', '{{.Repository}}:{{.Tag}}\t{{.Size}}'], text=True)
            images_info = [line.split('\t') for line in result.split('\n') if line]
            response = "\n".join([f"**{image_name}** - Size: {image_size}" for image_name, image_size in images_info])
        
        elif action == "pull" and image_name:
            subprocess.check_output(['docker', 'pull', image_name])
            response = f"Image `{image_name}` has been pulled successfully."
        
        elif action == "remove" and image_name:
            subprocess.check_output(['docker', 'rmi', image_name])
            response = f"Image `{image_name}` has been removed successfully."
        
        else:
            await ctx.respond("Please provide a valid action and image name if required.")
            return

        embed = discord.Embed(
            title="**__Docker Image Management__**",
            description=response,
            color=discord.Colour.blurple(),
        )
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        await ctx.respond(f"Error executing Docker command: {e}")

@docker_management.command(description="Prune Docker images.")
async def prune(ctx, all: discord.Option(bool, description="Prune all Docker images (including unused ones)", required=True)):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    log_command(ctx.author.id, ctx.author.name, "prune", {"all": all})

    try:
        await ctx.defer()
        prune_command = ['docker', 'image', 'prune', '-f']
        if all:
            prune_command.append('-a')
        
        subprocess.check_output(prune_command)
        embed = discord.Embed(
            title="**__Docker Image Pruning__**",
            description="Unused Docker images have been pruned successfully.",
            color=discord.Colour.blurple(),
        )
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        await ctx.respond(f"Error executing Docker command: {e}")

active_log_streams = {}  # Track active log streams

# Modify the follow command
@bot.slash_command(description="Follow live logs of a Docker container.")
async def follow(ctx, container_name: discord.Option(str, autocomplete=get_container_names)):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    log_command(ctx.author.id, ctx.author.name, "follow", {"container_name": container_name})

    # Check if the user already has an active log stream
    if ctx.author.id in active_log_streams:
        await ctx.respond("You already have an active log stream. Use `/stop` to stop it before starting a new one.")
        return

    # Start streaming logs from the current time
    await ctx.respond(f"📡 **Streaming logs for `{container_name}`...** (Type `/stop` to stop logging)")
    await follow_stream_logs(ctx, container_name)

# Add a stop command
@bot.slash_command(description="Stop an active log stream.")
async def stop(ctx):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    if ctx.author.id not in active_log_streams:
        await ctx.respond("You do not have an active log stream to stop.")
        return

    # Stop the log stream
    process = active_log_streams[ctx.author.id]["process"]
    process.terminate()
    del active_log_streams[ctx.author.id]

    await ctx.respond("✅ Log streaming stopped.")

async def follow_stream_logs(ctx, container_name):
    try:
        process = await asyncio.create_subprocess_exec(
            "docker", "logs", "-f", "--since", "0s", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        active_log_streams[ctx.author.id] = {"process": process, "container_name": container_name}

        buffer = []
        current_length = 0
        MAX_MESSAGE_LENGTH = 1900  # Leave some room for the code block formatting

        while True:
            line = await process.stdout.readline()
            if not line:
                break

            decoded_line = line.decode().strip()
            line_length = len(decoded_line) + 1  # +1 for the newline

            # If adding this line would exceed the limit, send what we have and start a new buffer
            if current_length + line_length > MAX_MESSAGE_LENGTH:
                if buffer:
                    await ctx.send(f"```{chr(10).join(buffer)}```")
                    buffer = []
                    current_length = 0
                
                # If a single line is longer than the maximum length, split it
                if line_length > MAX_MESSAGE_LENGTH:
                    # Split the long line into chunks
                    chunks = [decoded_line[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(decoded_line), MAX_MESSAGE_LENGTH)]
                    for chunk in chunks:
                        await ctx.send(f"```{chunk}```")
                else:
                    buffer.append(decoded_line)
                    current_length = line_length
            else:
                buffer.append(decoded_line)
                current_length += line_length

            # If we have accumulated a decent number of lines, send them
            if len(buffer) >= 10:
                await ctx.send(f"```{chr(10).join(buffer)}```")
                buffer = []
                current_length = 0

        # Send any remaining logs
        if buffer:
            await ctx.send(f"```{chr(10).join(buffer)}```")

    except Exception as e:
        await ctx.respond(f"⚠️ Error streaming logs: {e}")

    finally:
        if ctx.author.id in active_log_streams:
            del active_log_streams[ctx.author.id]

@bot.slash_command(description="List all Docker containers.")
async def list(ctx):
    role = await check_permissions(ctx, "dev")
    if not role:
        return

    try:
        result = subprocess.check_output(['docker', 'ps', '--all', '--format', '{{.Names}}\t{{.Status}}'], text=True)
        containers = [line.split('\t') for line in result.strip().split("\n") if line]

        embed = discord.Embed(title="📦 Docker Containers", color=discord.Colour.blue())
        for name, status in containers:
            embed.add_field(name=name, value=f"Status: `{status}`", inline=False)

        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        await ctx.respond(f"❌ Error: {e}")


@docker_management.command(description="Retrieve logs of a Docker container with optional filtering.")
async def logs(
    ctx, 
    container_name: discord.Option(str, description="Select a Docker container", autocomplete=get_container_names),
    timeframe: discord.Option(str, description="Specify timeframe (e.g., 10m for minutes, 2h for hours)"),
    search: discord.Option(str, description="Optional: Filter logs by keyword", required=False) = None
):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    log_command(ctx.author.id, ctx.author.name, "logs", {"container_name": container_name, "timeframe": timeframe, "search": search})

    try:
        await ctx.defer()

        # Validate timeframe format
        if not timeframe.endswith(('m', 'h')):
            await ctx.respond("Invalid timeframe format. Use 'm' for minutes or 'h' for hours (e.g., '15m', '2h').")
            return

        time_value = timeframe[:-1]
        if not time_value.isdigit():
            await ctx.respond("Timeframe should be a number followed by 'm' or 'h' (e.g., '10m', '2h').")
            return

        # Fetch logs
        logs = subprocess.check_output(
            ['docker', 'logs', '--since', timeframe, container_name],
            text=True,
            stderr=subprocess.STDOUT
        )

        # Apply search filter if provided
        if search and search.strip():
            filtered_logs = []
            for line in logs.splitlines():
                if search.lower() in line.lower():
                    filtered_logs.append(line)
            
            if not filtered_logs:
                await ctx.respond(f"No logs containing `{search}` found for `{container_name}` in the last {timeframe}.")
                return
                
            logs = "\n".join(filtered_logs)

        if not logs.strip():
            await ctx.respond(f"No logs available for `{container_name}` in the last {timeframe}.")
            return

        # Create embed for initial response
        embed = discord.Embed(
            title=f"📜 Docker Logs: `{container_name}`",
            description=f"**Timeframe:** Last {timeframe}" + (f"\n**Filter:** `{search}`" if search else ""),
            color=discord.Colour.blue()
        )
        
        # Add log summary information
        log_line_count = logs.count('\n') + 1 if logs.strip() else 0
        embed.add_field(name="Summary", value=f"Found {log_line_count} log entries" + 
                                              (f" containing `{search}`" if search else ""))
        
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

        # Split and send logs in chunks to handle Discord's message length limit
        log_chunks = [logs[i:i+1900] for i in range(0, len(logs), 1900)]
        for chunk in log_chunks:
            if chunk.strip():  # Only send non-empty chunks
                await ctx.send(f"```{chunk}```")

    except subprocess.CalledProcessError as e:
        error_embed = discord.Embed(
            title="⚠️ Error Fetching Logs",
            description=f"Failed to retrieve logs for `{container_name}`: {str(e)}",
            color=discord.Colour.red()
        )
        error_embed.set_footer(text=get_current_time())
        await ctx.respond(embed=error_embed)


@docker_management.command(description="Set resource limits for a Docker container.")
async def limit(
    ctx,
    container_name: discord.Option(str, description="Select a Docker container", autocomplete=get_container_names),
    cpu: discord.Option(str, description="CPU limit (e.g., 0.5 for 50% of a core, 2 for 2 cores)", required=False) = None,
    memory: discord.Option(str, description="Memory limit (e.g., 512m, 1g)", required=False) = None
):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    log_command(ctx.author.id, ctx.author.name, "limit", {"container_name": container_name, "cpu": cpu, "memory": memory})

    # Check if at least one limit option is provided
    if cpu is None and memory is None:
        await ctx.respond("Please specify at least one limit (cpu or memory).")
        return

    try:
        await ctx.defer()

        # First check if container exists and is running
        container_status = subprocess.check_output(['docker', 'inspect', '-f', '{{.State.Status}}', container_name], text=True).strip()
        if container_status != 'running':
            await ctx.respond(f"Container `{container_name}` is not running. Resource limits can only be updated for running containers.")
            return

        # Prepare update command
        update_cmd = ['docker', 'update']
        
        # Add CPU limit if provided
        if cpu is not None:
            try:
                # Validate CPU format
                float(cpu)  # This will raise ValueError if cpu isn't a valid number
                update_cmd.extend(['--cpus', cpu])
            except ValueError:
                await ctx.respond(f"Invalid CPU limit format: `{cpu}`. Please use a number (e.g., 0.5, 2).")
                return

        # Add memory limit if provided
        if memory is not None:
            # Validate memory format (simple check)
            if not memory[-1].lower() in ['b', 'k', 'm', 'g'] and not memory.isdigit():
                await ctx.respond(f"Invalid memory limit format: `{memory}`. Please use a format like 512m or 1g.")
                return
            update_cmd.extend(['--memory', memory])

        # Add container name to command
        update_cmd.append(container_name)
        
        # Execute update command
        result = subprocess.check_output(update_cmd, stderr=subprocess.STDOUT, text=True)
        
        # Create response embed
        embed = discord.Embed(
            title=f"✅ Resource Limits Updated: `{container_name}`",
            color=discord.Colour.green()
        )
        
        # Add details fields
        if cpu is not None:
            embed.add_field(name="CPU Limit", value=f"`{cpu}` cores", inline=True)
        
        if memory is not None:
            embed.add_field(name="Memory Limit", value=f"`{memory}`", inline=True)
            
        # Get current resource usage for comparison
        stats = subprocess.check_output(
            ['docker', 'stats', '--no-stream', '--format', '{{.CPUPerc}} {{.MemUsage}}', container_name],
            text=True
        ).strip().split()
        
        if len(stats) >= 2:
            cpu_usage, mem_usage = stats[0], stats[1]
            embed.add_field(name="Current Usage", value=f"CPU: `{cpu_usage}` | Memory: `{mem_usage}`", inline=False)
        
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        error_embed = discord.Embed(
            title="⚠️ Error Setting Resource Limits",
            description=f"Failed to update limits for `{container_name}`: {str(e.output if hasattr(e, 'output') else e)}",
            color=discord.Colour.red()
        )
        error_embed.set_footer(text=get_current_time())
        await ctx.respond(embed=error_embed)


@bot.slash_command(description="Get system-wide Docker information.")
async def system(ctx):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    log_command(ctx.author.id, ctx.author.name, "system", {})

    try:
        await ctx.defer()
        system_info = subprocess.check_output(["docker", "system", "df"], text=True)
        container_count = subprocess.check_output(["docker", "ps", "-q"], text=True).count("\n")

        embed = discord.Embed(
            title="📊 **Docker System Info**",
            description=f"🖥️ **Total Running Containers:** `{container_count}`",
            color=discord.Colour.blue()
        )
        embed.add_field(name="📦 **Resource Usage:**", value=f"```{system_info.strip()}```", inline=False)
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        await ctx.respond(f"⚠️ Error fetching system info: {e}")

@bot.slash_command(description="Check the health of a Docker container.")
async def health(ctx, container_name: discord.Option(str, autocomplete=get_container_names)):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    log_command(ctx.author.id, ctx.author.name, "health", {"container_name": container_name})

    try:
        await ctx.defer()
        health_status = subprocess.check_output(
            ["docker", "inspect", "--format={{.State.Health.Status}}", container_name],
            text=True
        ).strip()

        color = discord.Colour.green() if health_status == "healthy" else \
                discord.Colour.red() if health_status == "unhealthy" else \
                discord.Colour.orange()

        embed = discord.Embed(
            title=f"🩺 **Health Check: `{container_name}`**",
            description=f"🔍 **Status:** `{health_status.upper()}`",
            color=color
        )
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError:
        await ctx.respond(f"⚠️ `{container_name}` does not support health checks or does not exist.")

async def alert_monitor():
    await bot.wait_until_ready()
    alert_channel = bot.get_channel(ALERT_CHANNEL_ID)
    
    if not alert_channel:
        print(f"⚠️ ALERT CHANNEL NOT CONFIGURED! ID: {ALERT_CHANNEL_ID}")
        return

    print(f"✅ Monitoring containers... Alerts will be sent to #{alert_channel.name}")

    while not bot.is_closed():
        try:
            stats_output = subprocess.check_output(
                ["docker", "stats", "--no-stream", "--format", "{{.Name}} {{.CPUPerc}} {{.MemUsage}}"],
                text=True
            ).strip().split("\n")

            for stat in stats_output:
                parts = stat.split()
                if len(parts) < 3:
                    continue

                container_name, cpu_usage, mem_usage = parts[0], parts[1].strip('%'), parts[2]

                try:
                    cpu_usage = float(cpu_usage)
                except ValueError:
                    continue

                if cpu_usage > ALERT_THRESHOLD:
                    last_alert_time = alerted_containers.get(container_name)
                    
                    if last_alert_time and (datetime.now() - last_alert_time).seconds < 300:
                        continue

                    embed = discord.Embed(
                        title=f"🚨 **High CPU Alert: `{container_name}`**",
                        description=f"🔥 **CPU Usage:** `{cpu_usage}%`\n🖥️ **Memory Usage:** `{mem_usage}`",
                        color=discord.Colour.red()
                    )
                    embed.set_footer(text=get_current_time())
                    
                    await alert_channel.send(embed=embed)
                    alerted_containers[container_name] = datetime.now()

                elif container_name in alerted_containers:
                    del alerted_containers[container_name]

        except subprocess.CalledProcessError as e:
            print(f"❌ Error fetching container stats: {e}")

        await asyncio.sleep(60)

@bot.slash_command(description="Ping the bot.")
async def ping(ctx):
    await ctx.respond(f"`🏓 Pong!`")

@bot.slash_command(description="Get system uptime.")
async def uptime(ctx):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    log_command(ctx.author.id, ctx.author.name, "uptime", {})

    try:
        await ctx.defer()
        if platform.system().lower() == 'linux':
            result = subprocess.check_output(['uptime', '-p'], text=True)
        elif platform.system().lower() == 'darwin':
            result = subprocess.check_output(['uptime'], text=True)
        else:
            result = "System uptime command not supported on this platform."

        embed = discord.Embed(
            title="**__System Uptime__**",
            description=f"**Uptime:** `{result.strip()}`",
            color=discord.Colour.blurple(),
        )
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except subprocess.CalledProcessError as e:
        await ctx.respond(f"Error retrieving system uptime: {e}")

@bot.slash_command(description="Audit command executions within a specified timeframe.")
async def audit(ctx, timeframe: discord.Option(str, description="Specify timeframe (e.g., 10m for minutes, 2h for hours, 1d for days, 1mon for months)")):
    if ctx.author.id not in config["allowed_user_ids"]:
        await ctx.respond("You are not authorized to use this bot.")
        return

    try:
        await ctx.defer()

        # Validate timeframe format
        if not timeframe.endswith(('m', 'h', 'd', 'mon')):
            await ctx.respond("Invalid timeframe format. Use 'm' for minutes, 'h' for hours, 'd' for days, or 'mon' for months (e.g., '15m', '2h', '1d', '1mon').")
            return

        time_value = timeframe[:-1]
        if not time_value.isdigit():
            await ctx.respond("Timeframe should be a number followed by 'm', 'h', 'd', or 'mon' (e.g., '10m', '2h', '1d', '1mon').")
            return

        # Calculate the cutoff time
        now = datetime.now()
        if timeframe.endswith('m'):
            cutoff_time = now - timedelta(minutes=int(time_value))
        elif timeframe.endswith('h'):
            cutoff_time = now - timedelta(hours=int(time_value))
        elif timeframe.endswith('d'):
            cutoff_time = now - timedelta(days=int(time_value))
        elif timeframe.endswith('mon'):
            cutoff_time = now - timedelta(days=int(time_value) * 30)

        # Read and filter the audit log
        audit_entries = []
        try:
            with open(AUDIT_LOG_FILE, "r") as log_file:
                for line in log_file:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time >= cutoff_time:
                        audit_entries.append(entry)
        except FileNotFoundError:
            await ctx.respond("No audit logs found.")
            return

        if not audit_entries:
            await ctx.respond(f"No commands executed in the last {timeframe}.")
            return

        # Format the audit log entries
        formatted_entries = []
        for entry in audit_entries:
            formatted_entries.append(
                f"**{entry['username']}** (`{entry['user_id']}`) executed `/{entry['command']}` with args `{entry['args']}` at `{entry['timestamp']}`"
            )

        # Create embed for the response
        embed = discord.Embed(
            title=f"📜 Audit Log (Last {timeframe})",
            description="\n".join(formatted_entries),
            color=discord.Colour.blue()
        )
        embed.set_footer(text=get_current_time())
        await ctx.respond(embed=embed)

    except Exception as e:
        await ctx.respond(f"⚠️ Error fetching audit logs: {e}")

bot.run(config["token"])