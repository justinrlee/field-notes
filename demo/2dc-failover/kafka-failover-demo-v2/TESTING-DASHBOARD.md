# Testing the single-page dashboard

Nothing here has been run. Do these on the EC2 instance and your workstation.

1. Create the venv and `.env` as in `README.md` (this folder is a separate copy
   of the project, so it needs its own `.venv` and `.env`).
2. `chmod +x run-all.sh run-dashboard.sh`, then `./run.sh preflight`.
3. `./run-all.sh`. Expected: "Started: ..." and an http.server log line when the
   page is first loaded.
4. Open `http://UI_HOST:8090`. Allow TCP 8081-8084 and 8090 from your
   workstation (or tunnel those five ports).

## Checks

| What to do | Expected |
|---|---|
| Load the page | Four panels. Header shows four green link dots. Each panel goes from "Connecting" to "Connected" |
| Header, cluster line | One cluster ID chip, "4 of 4 clients" |
| Header, brokers | One chip per broker with "n of 4 connected" (idle brokers show 0 and that is normal) |
| Producers | Delivered counts rise, tiles turn green |
| Consumers | Received counts rise, tiles turn blue, Missing stays 0 |
| Stop the gateway | Panels turn amber with outage timers. Producer "Waiting" rises. Link dots stay green |
| Restore it | "Back online" with total outage time, then "Connected" |
| Switch clusters | Cluster line shows the new ID. If clients briefly disagree, the chips turn blue and list which clients are on which |
| Kill one client (`kill` its uvicorn process, run separately with `./run.sh`) | Its link dot turns red and its panel dims. The other three keep updating. It recovers when the client restarts |
| Open `http://UI_HOST:8081` | The original single-client UI still works |

## Known limits

- Producer controls (send 1/100, rate slider) and the per-client event timeline
  and settings are not on this page. Use the individual UIs for those.
- The page assumes the default ports. Override with
  `?host=name&producer-tuned=9001` in the URL.
