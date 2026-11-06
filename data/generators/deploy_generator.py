"""
RecallOps - Synthetic Deployment Generator
Member 3: Database & Data Engineering

Generates approximately 400 realistic deployments for Kartly across 6 months.
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

# Realistic commit messages categorized by service
DEPLOY_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "checkout-api": [
        {"summary": "feat(checkout): add UPI intent flow for mobile web checkout", "config": False, "diff": "+upi_flow_v2.py"},
        {"summary": "perf(db): optimize connection pool parameters for checkout service", "config": True, "diff": "max_connections: 50 -> 65"},
        {"summary": "fix(cart): prevent race condition during simultaneous cart item updates", "config": False, "diff": "+mutex_lock_handler"},
        {"summary": "config(unleash): enable fast checkout flow flag for Bangalore users", "config": True, "diff": "flag: enable_quick_checkout_v2: true"},
        {"summary": "refactor(checkout): streamline order confirmation payload schema", "config": False, "diff": "~order_dto.py"},
        {"summary": "chore(deps): bump psycopg2-binary and sqlalchemy dependencies", "config": False, "diff": "requirements.txt: psycopg2==2.9.12"},
        {"summary": "feat(coupon): add validation logic for festive discount vouchers", "config": False, "diff": "+voucher_validator.py"},
        {"summary": "fix(timeout): add circuit breaker on address verification RPC", "config": False, "diff": "+pybreaker_circuit"},
    ],
    "payments-svc": [
        {"summary": "feat(payments): integrate Razorpay UPI AutoPay recurring subscription", "config": False, "diff": "+autopay_controller.py"},
        {"summary": "config(pki): update TLS cipher suites and renew mTLS cert configs", "config": True, "diff": "ssl_protocols: TLSv1.2 TLSv1.3"},
        {"summary": "fix(webhook): handle out-of-order payment confirmation webhooks", "config": False, "diff": "+idempotent_event_store"},
        {"summary": "perf(gateway): implement fallback router to PayU when Razorpay p99 > 3s", "config": False, "diff": "+smart_gateway_router.py"},
        {"summary": "chore(deps): update payment gateway SDK to latest security patch", "config": False, "diff": "razorpay-client==1.4.2"},
        {"summary": "config(routing): adjust traffic split: 70% Razorpay, 30% PayU", "config": True, "diff": "routing_weights: {razorpay: 70, payu: 30}"},
        {"summary": "feat(refunds): implement instant refund API via IMPS banking rails", "config": False, "diff": "+instant_refund_worker.py"},
        {"summary": "fix(retry): implement exponential backoff with jitter on bank status check", "config": False, "diff": "+tenacity_retry_config"},
    ],
    "inventory-svc": [
        {"summary": "feat(inventory): add batch stock reservation API for flash sales", "config": False, "diff": "+batch_reservation_api.py"},
        {"summary": "perf(cache): switch SKU cache serialization from JSON to MessagePack", "config": False, "diff": "+msgpack_serializer.py"},
        {"summary": "config(redis): tune maxmemory-policy to volatile-lru on ElastiCache", "config": True, "diff": "maxmemory-policy: volatile-lru"},
        {"summary": "fix(stock): fix negative stock deduction on cancelled order replay", "config": False, "diff": "+inventory_ledger_audit.py"},
        {"summary": "feat(warehouse): integrate WMS inventory sync event consumer", "config": False, "diff": "+wms_sync_consumer.py"},
        {"summary": "chore(db): add partial index on inventory_items(sku_id, warehouse_id)", "config": True, "diff": "migration: 202610_add_sku_warehouse_idx"},
        {"summary": "fix(deadlock): sort SKU IDs prior to acquiring row-level database locks", "config": False, "diff": "sorted(sku_ids)"},
    ],
    "search-svc": [
        {"summary": "feat(search): deploy hybrid lexical and semantic vector search model", "config": False, "diff": "+vector_search_engine.py"},
        {"summary": "perf(query): resolve N+1 eager loading on product category variants", "config": False, "diff": "~joinedload(Product.variants)"},
        {"summary": "config(es): adjust Elasticsearch index refresh interval to 30s", "config": True, "diff": "index.refresh_interval: 30s"},
        {"summary": "fix(suggester): sanitize special regex characters in search query input", "config": False, "diff": "+query_sanitizer.py"},
        {"summary": "feat(relevance): tune BM25 term frequency weights for Diwali catalog", "config": True, "diff": "bm25_b: 0.75, bm25_k1: 1.2"},
        {"summary": "chore(logging): configure logrotate maxsize and daily archive pruning", "config": True, "diff": "/etc/logrotate.d/search-svc"},
        {"summary": "fix(cache): introduce Redis query cache layer for top 1000 trending queries", "config": False, "diff": "+trending_cache.py"},
    ],
    "notification-svc": [
        {"summary": "feat(notify): add WhatsApp order dispatch notification template", "config": False, "diff": "+whatsapp_template_sender.py"},
        {"summary": "config(kafka): tune consumer max.poll.interval.ms to 600000ms", "config": True, "diff": "max.poll.interval.ms: 600000"},
        {"summary": "fix(sms): handle DLT template mismatch errors from telecom aggregator", "config": False, "diff": "+dlt_error_handler.py"},
        {"summary": "perf(batch): batch email dispatch payloads in chunks of 250", "config": False, "diff": "+batch_email_dispatcher.py"},
        {"summary": "chore(kafka): scale notification partition topic to 24 partitions", "config": True, "diff": "partitions: 24"},
        {"summary": "fix(rebalance): gracefully handle consumer revocation in SIGTERM hook", "config": False, "diff": "+sigterm_consumer_drain.py"},
    ],
    "delivery-eta-svc": [
        {"summary": "feat(eta): integrate realtime hyper-local traffic routing engine", "config": False, "diff": "+traffic_routing_matrix.py"},
        {"summary": "fix(geofence): correct pin code boundary validation for NCR region", "config": False, "diff": "+pincode_validator.py"},
        {"summary": "config(pricing): update festival delivery surge pricing matrix", "config": True, "diff": "surge_pricing_table.json"},
        {"summary": "perf(cache): cache rider dispatch locations with 5-second TTL in Redis", "config": False, "diff": "+rider_geohash_cache.py"},
        {"summary": "chore(deps): upgrade geopy and spatial computation libraries", "config": False, "diff": "geopy==2.4.1"},
        {"summary": "fix(timezone): enforce Asia/Kolkata timezone on delivery slot calculations", "config": False, "diff": "tz=ZoneInfo('Asia/Kolkata')"},
    ],
}


def generate_deployments(
    services: List[Dict[str, Any]],
    engineers: List[Dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    target_count: int = 400,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """
    Generate approximately target_count deployments distributed realistically over time.
    """
    random.seed(seed)
    total_seconds = int((end_time - start_time).total_seconds())
    
    # Generate random timestamp offsets
    offsets = sorted([random.randint(0, total_seconds) for _ in range(target_count)])
    
    deployments: List[Dict[str, Any]] = []
    
    service_map = {s["name"]: s["id"] for s in services}
    engineer_ids = [e["id"] for e in engineers]
    
    deploy_id = 1
    for offset in offsets:
        deploy_time = start_time + timedelta(seconds=offset)
        # Select service
        service_name = random.choice(list(DEPLOY_TEMPLATES.keys()))
        service_id = service_map[service_name]
        
        # Pick template
        templates = DEPLOY_TEMPLATES[service_name]
        template = random.choice(templates)
        
        # Pick author
        author_id = random.choice(engineer_ids)
        
        deployments.append({
            "id": deploy_id,
            "service_id": service_id,
            "author_id": author_id,
            "deployed_at": deploy_time,
            "summary": template["summary"],
            "config_change": template["config"],
            "diff_note": template["diff"],
        })
        deploy_id += 1
        
    return deployments
