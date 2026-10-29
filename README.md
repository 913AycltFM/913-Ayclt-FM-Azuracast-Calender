# 91.3 Ayclt FM — AzuraCast Calendar

Automated rolling 7-day programming calendar and Discord scheduled-event publisher for 91.3 Ayclt FM, HD2, and HD3.

## What it does

Connects to the 91.3 Ayclt FM AzuraCast API, retrieves station schedules, and generates an iCalendar (`.ics`) file. GitHub Actions runs every five minutes and can also be started manually.

## Included stations

- 91.3 Ayclt FM
- 91.3 Ayclt FM HD2
- 91.3 Ayclt FM HD3

## Features

- Rolling 7-day programming window
- Automatic updates every 5 minutes
- iCalendar (`.ics`) output and validation
- AzuraCast API retry handling and schedule filtering
- Duplicate-event protection
- UTC-compatible calendar timestamps
- Automatic GitHub release asset updates
- Discord Scheduled Events publishing, with create/update matching to avoid duplicate events
- DJ/streamer cover art fetched from the AzuraCast streamer artwork endpoint when the schedule data includes a streamer ID
- Event descriptions include station, show, DJ (when available), and listen link

## Generated calendar

The generated file is `azuracast_schedule.ics`. It can be imported into calendar applications that support iCalendar.

## Enable Discord scheduled events

In the repository, open **Settings → Secrets and variables → Actions → New repository secret** and add:

- `DISCORD_BOT_TOKEN` — the bot token from the Discord Developer Portal. Do not paste it into source code or chat.
- `DISCORD_GUILD_ID` — the ID of the Discord server where events should be published.

Keep the existing `AZURACAST_API_KEY` secret if your AzuraCast API requires it.

Invite the bot to the target server and give it the **Create Events** permission. The workflow uses Discord's API to create external scheduled events, and updates matching events on subsequent runs. The bot must be in the server. See the [official Discord Scheduled Events documentation](https://discord.com/developers/docs/resources/guild-scheduled-event).

After adding both secrets, open **Actions → Update AzuraCast Calendar → Run workflow** to test it. Check the run logs for event counts and any API errors.

**Important:** Existing Discord events are not automatically deleted if an item disappears from the AzuraCast schedule. The publisher skips events whose start time has already passed and only creates or updates upcoming events. If a schedule item does not expose a streamer ID, the event is published without DJ artwork.

## Automation

The workflow cron is:

```text
*/5 * * * *
```

Scheduled GitHub Actions runs may be delayed by GitHub during busy periods.

## API security

The AzuraCast API key and Discord bot token belong in GitHub Actions secrets only. Never commit secrets or print their values in logs.

## Validation

The workflow validates the generated calendar structure, event pairs, unique UIDs, and UTC timestamp fields before publishing.

Maintained for 91.3 Ayclt FM and its HD channels.
