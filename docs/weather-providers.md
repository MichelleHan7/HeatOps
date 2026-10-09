# Weather providers

| Source | Data kind | Credentials | Fallback |
|---|---|---|---|
| Phoenix bundled snapshot | Original FortyGuard ingestion fixture, dated 2026-08-24 | None | Already offline |
| FortyGuardProvider | Provider temperature product for requested date | FORTYGUARD_API_KEY | Explicit scenario data |
| OpenMeteoProvider | Hourly 2m forecast model / historical reanalysis | None for free noncommercial endpoint | Explicit scenario data |
| StaticProvider synthetic | Seeded test temperatures | None | None |

`WeatherProvider.fetch(jobs, requested_date, timezone)` returns `WeatherData`
(matrix and provenance). `fetch_with_fallback` preserves the fallback's actual
source/date and adds an unavailable-provider notice. It never converts a snapshot
into live weather. Open-Meteo requests UTC epoch timestamps across a padded date
range and converts them with zoneinfo. It retains raw timestamped values and
refuses missing required hours, nonfinite temperatures and repeated DST hours
that cannot fit the current HH:MM-only model. Hourly interpolation happens in the
existing Heat Load function. Cross-midnight service is not supported.

The cache is in-memory, keyed by endpoint/coordinates/date/timezone, with one-hour
TTL and validated coverage on retrieval; it is not a permanent weather archive.
The dashboard reuses a provider resource between runs. At most 25 locations per
request, bounded HTTP timeouts, no retry storms. A failed live request never changes
benchmark fixtures. A real historical Open-Meteo request for 2026-07-02 was verified
in this implementation session (25 hourly records returned). Tests use HTTP fakes.
No new FortyGuard live request was made without an authorized configured key.

## Official documentation and usage

Reviewed 2026-10-08:

- https://open-meteo.com/en/docs
- https://open-meteo.com/en/docs/historical-weather-api
- https://open-meteo.com/en/terms

The free service is for noncommercial use, subject to published call limits and
CC BY 4.0 attribution. The UI/export includes Open-Meteo attribution. Commercial
or higher-volume usage requires checking the provider's paid-service terms.
Historical reanalysis incorporates observations and modeling; it must not be
represented as independently measured local observations. Model grid coordinates
can differ from requested job coordinates and are retained in metadata.
