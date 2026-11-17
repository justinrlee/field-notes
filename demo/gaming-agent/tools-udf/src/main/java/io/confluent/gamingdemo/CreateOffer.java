package io.confluent.gamingdemo;

import java.util.Locale;
import java.util.UUID;
import org.apache.flink.table.functions.ScalarFunction;

/**
 * The action: create an in-game offer, free gift, or hint for a player.
 *
 * <p>Mock tool: validates the arguments and returns a JSON confirmation with no real side effect (the
 * analogue of freeze_account in the fraud demo). Free items ({@code free_boss_hint},
 * {@code free_comeback_gift}) are always priced 0. Paid SKUs must exist in the catalog and the discount
 * must be 0..30.
 */
public class CreateOffer extends ScalarFunction {
    // Generates a fresh offer id on every call.
    @Override
    public boolean isDeterministic() {
        return false;
    }

    public String eval(String playerId, String sku, Integer discountPct, Integer ttlSeconds, String channel) {
        int discount = discountPct == null ? 0 : discountPct;
        int ttl = ttlSeconds == null ? 900 : ttlSeconds;
        String ch = channel == null ? "in_game_popup" : channel;

        boolean free = Catalog.FREE_HINT.equals(sku) || Catalog.FREE_GIFT.equals(sku);
        double price = 0.0;
        if (!free) {
            Catalog.Sku s = Catalog.findSku(sku);
            if (s == null) {
                return rejected(playerId, sku, "unknown sku");
            }
            if (discount < 0 || discount > Catalog.MAX_DISCOUNT_PCT) {
                return rejected(playerId, sku, "discount_pct must be 0.." + Catalog.MAX_DISCOUNT_PCT);
            }
            price = s.price * (100 - discount) / 100.0;
        } else {
            discount = 100;
        }
        return String.format(Locale.ROOT,
            "{\"status\":\"CREATED\",\"offer_id\":%s,\"player_id\":%s,\"sku\":%s,\"discount_pct\":%d,"
                + "\"final_price\":%.2f,\"ttl_seconds\":%d,\"channel\":%s}",
            Catalog.q("offer-" + UUID.randomUUID().toString().substring(0, 8)), Catalog.q(playerId),
            Catalog.q(sku), discount, price, ttl, Catalog.q(ch));
    }

    private static String rejected(String playerId, String sku, String reason) {
        return "{\"status\":\"REJECTED\",\"player_id\":" + Catalog.q(playerId) + ",\"sku\":" + Catalog.q(sku)
            + ",\"reason\":" + Catalog.q(reason) + "}";
    }
}
