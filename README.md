# 91.3 Ayclt FM — AzuraCast Calendar

Automated rolling 7-day programming calendar for 91.3 Ayclt FM, HD2, and HD3. The calendar is generated from the AzuraCast API and can be subscribed to by calendar applications and ChronicleBot.

## Included stations

Only these three AzuraCast stations are included:

- 91.3 Ayclt FM
- 91.3 Ayclt FM HD2
- 91.3 Ayclt FM HD3

Gaming Central Radio and other stations are not included.

## Automatic updates

GitHub Actions runs the **Update AzuraCast Calendar** workflow every five minutes using this cron schedule:

```text
*/5 * * * *
```

The workflow can also be started manually from **Actions → Update AzuraCast Calendar → Run workflow**.

Each run fetches the upcoming seven days of schedules for all three stations, rebuilds the iCalendar file, validates it, and commits the updated file when its contents change. GitHub may delay scheduled workflows during busy periods, so five minutes is the configured interval, not a guaranteed exact execution time.

## Generated calendar

The workflow generates:

- `azuracast_schedule.ics` — the calendar feed
- A rolling seven-day window of upcoming events
- UTC-compatible iCalendar timestamps and stable event UIDs

**Raw calendar feed:**

[Subscribe to the 91.3 Ayclt FM calendar](https://raw.githubusercontent.com/913AycltFM/913-Ayclt-FM-Azuracast-Calender/refs/heads/main/azuracast_schedule.ics)

Use the raw feed URL when adding the calendar to a calendar app or configuring ChronicleBot to read the calendar.

## DJ and station artwork

For each event, the exporter tries to match the scheduled DJ to that station's AzuraCast streamer profile and uses the streamer's artwork URL. If no DJ artwork can be matched, it uses that station's configured fallback cover art.

The ICS event includes ChronicleBot cover metadata in the DESCRIPTION front matter and an iCalendar `IMAGE` property for compatible calendar clients. Some calendar applications do not display remote event images.

## ChronicleBot

ChronicleBot is the calendar integration used to create Discord scheduled events from this iCalendar feed. Configure ChronicleBot to subscribe to the raw calendar URL above. When the calendar updates, ChronicleBot can read the updated schedule and event cover metadata.

If artwork changes for an event that ChronicleBot has already imported, it may be necessary to remove the old Discord event and let ChronicleBot recreate it so the new cover is applied.

## API security

Store the AzuraCast API key and Discord bot token in GitHub Actions secrets only. Never commit secrets or print their values in workflow logs.

## Validation

Before publishing, the workflow validates the generated calendar structure, event pairs, unique UIDs, and UTC timestamp fields.

Maintained for 91.3 Ayclt FM and its HD channels.
