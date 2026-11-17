"""Generates synthetic player combat events, activity events, and profile upserts.

Normal play only: every simulated player stays BELOW the struggle filter (DESIGN.md §4), so the
agent stays quiet until a trigger button (game-trigger/) injects a struggle burst. Dedicated demo
players (gamedata.DEMO_PLAYERS) get their profiles seeded but are never simulated.

On startup all profiles (simulated + demo) are upserted to `player_profiles`. They are
upserted again whenever they change (PURCHASE, level-up) and re-emitted every
--heartbeat-secs so the versioned table's watermark never stalls (DESIGN.md §4, enrichment).

Profiles are in-memory state: restarting the producer re-seeds them to fresh initial values.

Run after `terraform apply` (which writes .env). Options:
  --speed N            scene-rate multiplier (default 1.0). Effective gap between a player's scenes
                       never drops below MIN_SCENE_GAP_S, so a higher speed can't merge scenes
                       into one session window.
  --heartbeat-secs N   profile re-emit interval (default 5)
  --seed-only          upsert all profiles once and exit
  --duration N         stop after N seconds (default: run until interrupted)
  --rng-seed N         make the simulation repeatable
"""

import argparse
import heapq
import itertools
import random
import time
import uuid

import gamedata
import kafka_io
from kafka_io import TOPIC_ACTIVITY, TOPIC_COMBAT, now_ms

# A scene lasts up to ~10 s and the SESSION gap is ~10-15 s, so keep a player's scenes at least
# this far apart (measured from the end of the previous scene) or they would merge into one window.
MIN_SCENE_GAP_S = 25.0


def short_id():
    return uuid.uuid4().hex[:12]


class Simulator:
    def __init__(self, producer, serializers, key_serializers, rng, speed=1.0):
        self.producer = producer
        self.serializers = serializers
        self.key_serializers = key_serializers
        self.rng = rng
        self.speed = speed
        self._seq = itertools.count()
        self._queue = []  # heap of (due_epoch_s, seq, fn)
        self.simulated = gamedata.build_simulated_players(rng)
        self.demo = gamedata.build_demo_players()
        self.by_game = {}
        for p in self.simulated:
            self.by_game.setdefault(p["game_id"], []).append(p)
            p.update(online=False, scenes=0, scenes_until_logout=rng.randint(4, 8),
                     scenes_until_levelup=rng.randint(8, 15))
        # Stagger first scenes across the first scene-gap so load is smooth from the start.
        self.next_scene = {
            p["player_id"]: time.time() + rng.uniform(0, gamedata.PERSONAS[p["persona"]]["scene_gap"][1] / speed)
            for p in self.simulated
        }

    # -- scheduling ---------------------------------------------------------

    def schedule(self, delay_s, fn):
        heapq.heappush(self._queue, (time.time() + delay_s, next(self._seq), fn))

    def run_due(self):
        now = time.time()
        while self._queue and self._queue[0][0] <= now:
            _, _, fn = heapq.heappop(self._queue)
            fn()

    # -- emitters (timestamps are stamped when the event is actually produced) -----------------

    def emit_combat(self, player, **fields):
        event = {
            "event_id": short_id(),
            "game_id": player["game_id"],
            "player_id": player["player_id"],
            "timestamp": now_ms(),
            **fields,
        }
        kafka_io.produce_event(self.producer, self.serializers, TOPIC_COMBAT, event)

    def emit_activity(self, player, activity_type, item_id=None, detail=None):
        event = {
            "event_id": short_id(),
            "game_id": player["game_id"],
            "player_id": player["player_id"],
            "activity_type": activity_type,
            "item_id": item_id,
            "detail": detail,
            "timestamp": now_ms(),
        }
        kafka_io.produce_event(self.producer, self.serializers, TOPIC_ACTIVITY, event)

    def emit_profile(self, player):
        kafka_io.produce_profile(self.producer, self.serializers, self.key_serializers, player)

    def emit_all_profiles(self):
        for p in self.simulated + self.demo:
            self.emit_profile(p)

    # -- scenes -------------------------------------------------------------

    def _pick_source(self, player, zone):
        """Return (source_id, source_type) for one fight."""
        if player["game_id"] == "starlane_arena" and self.rng.random() < 0.3:
            others = [p for p in self.by_game[player["game_id"]] if p is not player]
            return self.rng.choice(others)["player_id"], "PVP_PLAYER"
        if self.rng.random() < 0.15:
            return zone["boss"], "BOSS"
        return self.rng.choice(zone["enemies"]), "ENEMY"

    def play_scene(self, player):
        """Schedule one short burst of normal play; return its duration in seconds."""
        rng = self.rng
        persona = gamedata.PERSONAS[player["persona"]]
        zone = gamedata.zone_for_level(player["game_id"], player["level"])
        match_id = f"m-{short_id()[:8]}"
        t = 0.0

        if not player["online"]:
            player["online"] = True
            self.schedule(t, lambda: self.emit_activity(player, "LOGIN", detail=player["region"]))
            t += rng.uniform(0.3, 1.0)

        deaths = 0
        for _ in range(rng.randint(*persona["fights"])):
            source_id, source_type = self._pick_source(player, zone)
            dies = deaths < persona["max_deaths"] and rng.random() < persona["death_p"]
            for _ in range(rng.randint(1, 3)):
                dmg = rng.randint(*persona["dmg"])
                self.schedule(t, lambda d=dmg, s=source_id, st=source_type: self.emit_combat(
                    player, match_id=match_id, event_type="DAMAGE_TAKEN", damage_amount=d, source_id=s,
                    source_type=st, zone_id=zone["id"], player_level=player["level"]))
                t += rng.uniform(0.2, 0.6)
            if dies:
                deaths += 1
                killing = rng.randint(*persona["dmg"])
                self.schedule(t, lambda d=killing, s=source_id, st=source_type: self.emit_combat(
                    player, match_id=match_id, event_type="DEATH", damage_amount=d, source_id=s,
                    source_type=st, zone_id=zone["id"], player_level=player["level"]))
                t += rng.uniform(0.5, 1.0)
                self.schedule(t, lambda s=source_id, st=source_type: self.emit_combat(
                    player, match_id=match_id, event_type="REVIVE", damage_amount=0, source_id=s,
                    source_type=st, zone_id=zone["id"], player_level=player["level"]))
            t += rng.uniform(0.3, 0.9)

        skus = gamedata.GAMES[player["game_id"]]["skus"]
        if rng.random() < persona["store_view_p"]:
            sku = rng.choice(skus)["sku"]
            self.schedule(t, lambda s=sku: self.emit_activity(player, "STORE_VIEW", item_id=s))
            t += rng.uniform(0.3, 0.8)
        if rng.random() < 0.1:
            sku = rng.choice(skus)["sku"]
            self.schedule(t, lambda s=sku: self.emit_activity(player, "ITEM_EQUIP", item_id=s))
            t += rng.uniform(0.2, 0.5)
        if rng.random() < persona["quest_p"]:
            # At most one quest outcome per scene, so quest_fails <= 1 (never combines with
            # deaths >= 4 to trip the filter; deaths are capped by persona["max_deaths"]).
            kind = "QUEST_FAIL" if rng.random() < persona["quest_fail_p"] else "QUEST_COMPLETE"
            self.schedule(t, lambda k=kind: self.emit_activity(player, k, detail=f"quest-{zone['id']}"))
            t += rng.uniform(0.3, 0.8)
        if rng.random() < persona["purchase_p"]:
            t = self._schedule_purchase(player, t)

        player["scenes"] += 1
        player["scenes_until_levelup"] -= 1
        if player["scenes_until_levelup"] <= 0:
            player["scenes_until_levelup"] = rng.randint(8, 15)
            player["level"] += 1
            self.schedule(t, lambda: self.emit_profile(player))
            t += 0.1

        player["scenes_until_logout"] -= 1
        if player["scenes_until_logout"] <= 0:
            player["scenes_until_logout"] = rng.randint(4, 8)
            player["online"] = False
            self.schedule(t, lambda: self.emit_activity(player, "LOGOUT"))
            t += 0.1
        return t

    def _schedule_purchase(self, player, t):
        """PURCHASE activity, then the profile upsert with raised spend. Skips capped/owned items."""
        game_id = player["game_id"]
        options = [s for s in gamedata.GAMES[game_id]["skus"] if s["sku"] not in player["owned_skus"]]
        cap = player["monthly_cap"]
        if cap is not None:
            options = [s for s in options if player["spend_30d"] + s["price"] <= cap]
        if not options:
            return t
        item = self.rng.choice(options)

        def purchase():
            self.emit_activity(player, "PURCHASE", item_id=item["sku"], detail=f"{item['price']:.2f}")
            player["lifetime_spend"] = round(player["lifetime_spend"] + item["price"], 2)
            player["spend_30d"] = round(player["spend_30d"] + item["price"], 2)
            player["last_purchase_ts"] = now_ms()
            player["owned_skus"] = player["owned_skus"] + [item["sku"]]
            if player["tier"] == "F2P":
                player["tier"] = "spender"

        self.schedule(t, purchase)
        self.schedule(t + 0.5, lambda: self.emit_profile(player))
        return t + 0.6

    # -- main loop ----------------------------------------------------------

    def tick(self):
        now = time.time()
        for p in self.simulated:
            if self.next_scene[p["player_id"]] <= now:
                duration = self.play_scene(p)
                gap = self.rng.uniform(*gamedata.PERSONAS[p["persona"]]["scene_gap"]) / self.speed
                self.next_scene[p["player_id"]] = now + duration + max(MIN_SCENE_GAP_S, gap)
        self.run_due()
        self.producer.poll(0)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate synthetic gaming events for Confluent Cloud")
    parser.add_argument("--speed", type=float, default=1.0, help="scene-rate multiplier (default 1.0)")
    parser.add_argument("--heartbeat-secs", type=float, default=5.0, help="profile re-emit interval")
    parser.add_argument("--seed-only", action="store_true", help="upsert all profiles once and exit")
    parser.add_argument("--duration", type=float, default=None, help="stop after N seconds")
    parser.add_argument("--rng-seed", type=int, default=None, help="make the simulation repeatable")
    return parser.parse_args()


def main():
    args = parse_args()
    rng = random.Random(args.rng_seed)
    producer = kafka_io.make_producer()
    serializers = kafka_io.build_serializers()
    key_serializers = kafka_io.build_key_serializers()
    sim = Simulator(producer, serializers, key_serializers, rng, speed=args.speed)

    print(f"Seeding {len(sim.simulated)} simulated + {len(sim.demo)} demo player profiles...", flush=True)
    sim.emit_all_profiles()
    producer.flush()
    if args.seed_only:
        print("Seed complete.", flush=True)
        return

    print(f"Generating normal play (speed {args.speed}x). Ctrl-C to stop.", flush=True)
    start = time.time()
    next_heartbeat = start + args.heartbeat_secs
    last_report = start
    try:
        while args.duration is None or time.time() - start < args.duration:
            sim.tick()
            now = time.time()
            if now >= next_heartbeat:
                sim.emit_all_profiles()
                next_heartbeat = now + args.heartbeat_secs
            if now - last_report >= 30:
                online = sum(1 for p in sim.simulated if p["online"])
                print(f"[{int(now - start)}s] {online}/{len(sim.simulated)} players online", flush=True)
                last_report = now
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        producer.flush(10)
        print("Producer stopped.", flush=True)


if __name__ == "__main__":
    main()
