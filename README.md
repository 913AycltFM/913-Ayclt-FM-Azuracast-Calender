# 91.3 AYCLT FM — AzuraCast Calendar

Automated rolling 7-day programming calendar for 91.3 AYCLT FM, HD2, and HD3.

## What it does

This project connects to the 91.3 AYCLT FM AzuraCast API, retrieves the station programming schedule, and generates an iCalendar (`.ics`) file.

The calendar is automatically updated **every 5 minutes** with GitHub Actions.

## Included stations

- 91.3 AYCLT FM
- 91.3 AYCLT FM HD2
- 91.3 AYCLT FM HD3

## Features

- Rolling 7-day programming window
- Automatic updates every 5 minutes
- AzuraCast API integration
- iCalendar (`.ics`) output
- Automatic API retry handling
- Duplicate-event protection
- Invalid schedule filtering
- UTC-compatible calendar timestamps
- Calendar validation before publishing
- Automatic GitHub release asset updates
- Detailed GitHub Actions logs

## Generated calendar

The generated calendar file is:

`azuracast_schedule.ics`

It can be imported into calendar applications and services that support the iCalendar format.

## Automation

The GitHub Actions workflow runs on this schedule:

```text
*/5 * * * *
```

The workflow can also be started manually from the **Actions** tab.

## API security

The AzuraCast API key is stored as a GitHub Actions secret named:

`AZURACAST_API_KEY`

The API key should never be placed directly in the source code or committed to the repository.

## Validation

Before the calendar is published, the workflow checks that:

- The iCalendar container is valid.
- Every event has matching `BEGIN:VEVENT` and `END:VEVENT` entries.
- Every event has a unique UID.
- Required UTC timestamp fields are valid.
- The generated calendar can be read successfully.

## 91.3 AYCLT FM

This project is maintained for the 91.3 AYCLT FM station programming schedule and its associated HD channels.
