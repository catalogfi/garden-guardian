# Garden Guardian 🌸

A comprehensive Docker container management bot for Discord, developed by [Catalog.fi](https://catalog.fi).

## Overview

Garden Guardian is a powerful Discord bot designed to simplify Docker container management through Discord's interface. This bot allows authorized users to monitor, control, and troubleshoot Docker containers using intuitive slash commands, helping DevOps teams collaborate more efficiently.

## Features

### Core Functionality
- **Container Management**: Start, stop, restart, pause, unpause, and delete containers
- **Real-time Monitoring**: Stream live container logs directly to Discord
- **Resource Control**: Set CPU and memory limits for containers
- **System Health**: Monitor container health status and system-wide Docker information

### Security & Permissions
- **Role-based Access Control**: Two permission levels (Admin and Dev)
- **Audit Logging**: Comprehensive logging of all commands and role changes
- **Secure Command Execution**: Input sanitization to prevent command injection

### Monitoring & Alerts
- **Resource Usage Alerts**: Receive notifications when containers exceed CPU thresholds
- **Health Checks**: Verify container health status with detailed reports

## Command Reference

### User Management
- `/add [role] [user]` - Add a user as an Admin or Dev (Admin only)
- `/remove [role] [user]` - Remove a user from Admin or Dev role (Admin only)
- `/roles` - View current Admins and Devs
- `/audit_roles` - View the role change audit log (Admin only)

### Container Management
- `/docker execute [action] [container_name]` - Execute Docker container management commands
- `/docker logs [container_name] [timeframe] [search]` - Retrieve filtered container logs
- `/docker limit [container_name] [cpu] [memory]` - Set resource limits for a container
- `/docker images [action] [image_name]` - Manage Docker images (list, pull, remove)
- `/docker prune [all]` - Prune Docker images
- `/list` - List all Docker containers
- `/follow [container_name]` - Follow live logs of a Docker container
- `/stop` - Stop an active log stream
- `/health [container_name]` - Check the health of a Docker container

### System Information
- `/system` - Get system-wide Docker information
- `/uptime` - Get system uptime
- `/ping` - Check if the bot is responsive
- `/audit [timeframe]` - Review command execution history

## Setup Instructions

### Prerequisites
- Docker installed on your host machine
- Discord Bot Token
- Appropriate server permissions to add and configure bots

### Installation

1. Clone this repository to your server
```bash
git clone https://github.com/catalogfi/garden-guardian.git
cd garden-guardian
```

2. Create a configuration file at `config/config.json`:
```json
{
  "token": "YOUR_DISCORD_BOT_TOKEN",
  "bot_name": "Garden Guardian",
  "timezone_offset": 0,
  "admins": [123456789012345678],
  "devs": [987654321098765432],
  "allowed_user_ids": [123456789012345678, 987654321098765432],
  "alert_channel_id": 123456789012345678,
  "status": {
    "type": "watching",
    "message": "your containers grow 🌱"
  }
}
```

3. Add a bot avatar image named `avatar.png` to the root directory

4. Build and run the Docker container:
```bash
docker run -d \
  --name garden-guardian \
  --restart always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/config:/usr/src/app/config \
  ghcr.io/catalogfi/garden-guardian:latest

```

To deploy the `garden-guardian` container from GitHub Container Registry (GHCR), use the provided `docker-compose.yml` file.  

#### **Steps to Run:**  
1. Ensure Docker and Docker Compose are installed on your system.  
2. Pull the latest image and start the container:  
   ```sh
   docker-compose up -d
   ```
3. The container will automatically restart if it stops, ensuring continuous operation.  

#### **Volumes Used:**  
- `/var/run/docker.sock:/var/run/docker.sock`: Allows the container to interact with the Docker daemon.  
- `./config:/usr/src/app/config`: Mounts the local `config` directory for configuration files.  

To stop the container, run:  
```sh
docker-compose down
```  

### Bot Setup

1. Create a new application in the [Discord Developer Portal](https://discord.com/developers/applications)
2. Add a bot to your application
3. Enable the Server Members Intent
4. Generate an invite link with the `bot` and `applications.commands` scopes
5. Invite the bot to your server

## Security Considerations

- The bot requires access to the Docker socket, which is a privileged resource
- Only add trusted users as Admins as they can execute potentially destructive Docker commands
- Command inputs are sanitized with `shlex.quote()` to prevent command injection
- All commands are logged for audit purposes

## Troubleshooting

### Common Issues

- **Bot not responding to commands**: Ensure you've properly synced slash commands by checking the console output when the bot starts up
- **Permission errors**: Verify Docker socket permissions and that the container has appropriate access
- **Command not found**: Ensure you're using the correct command syntax with appropriate parameters

### Log Monitoring

Use the `/follow` command to stream container logs directly to Discord for real-time debugging.

## Advanced Configuration

### Alert Thresholds

The `ALERT_THRESHOLD` constant (default: 50%) in the code determines when CPU usage alerts are triggered. Modify this value to adjust sensitivity.

### Log Retention

To modify log retention policies, adjust the Docker log options for your containers:
```bash
docker run --log-opt max-size=10m --log-opt max-file=3 your-container
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

---

Developed by [Catalog.fi](https://catalog.fi) 