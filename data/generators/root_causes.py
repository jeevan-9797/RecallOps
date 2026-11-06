"""
RecallOps - Root Cause Families & Incident Patterns
Member 3: Database & Data Engineering

Defines 8 realistic recurring root-cause families with authentic operational metrics,
log messages (HikariCP, Redis, Nginx, PostgreSQL, etc.), and fix attempts.
"""

from typing import Any, Dict, List

ROOT_CAUSE_FAMILIES: Dict[str, Dict[str, Any]] = {
    "db_pool": {
        "name": "Database Connection Pool Exhaustion",
        "services": ["checkout-api", "inventory-svc", "payments-svc"],
        "severities": ["P1", "P2"],
        "alert": {
            "metric": "db_connection_pool_active_ratio",
            "threshold": 0.90,
            "value_range": (0.95, 1.00),
            "payload_template": {
                "pool_name": "HikariCP-MainPool",
                "max_connections": 50,
                "active_connections": 50,
                "pending_threads": 42,
            },
        },
        "log_sources": ["HikariCP", "PostgreSQL", "DatabaseConnectionPool", "GunicornWorker"],
        "log_messages": [
            ("WARN", "HikariCP", "HikariPool-1 - Connection is not available, request timed out after 30000ms (total=50, active=50, idle=0, waiting=38)"),
            ("ERROR", "PostgreSQL", "FATAL: remaining connection slots are reserved for non-replication superuser connections"),
            ("ERROR", "DatabaseConnectionPool", "org.postgresql.util.PSQLException: FATAL: sorry, too many clients already"),
            ("WARN", "GunicornWorker", "Worker timeout (pid:4981) - slow query or blocked DB connection acquisition detected"),
            ("INFO", "HikariCP", "HikariPool-1 - Pool stats (total=50, active=50, idle=0, waiting=65)"),
            ("ERROR", "checkout-api", "InternalServerError: 500 - could not obtain JDBC connection from datasource within timeout"),
            ("WARN", "DatabaseConnectionPool", "Connection leak detection triggered for connection #412; stacktrace captured at checkout_dao.py:84"),
            ("INFO", "PostgreSQL", "LOG: process 29140 still waiting for ExclusiveLock on relation 'orders' of database 'kartly_db'"),
        ],
        "failed_fixes": [
            "Restarted service deployment pods (connections exhausted again within 2 minutes)",
            "Flushed Redis session cache (no impact on PostgreSQL connection saturation)",
            "Increased pod horizontal replica count from 4 to 8 (worsened DB connection contention)",
        ],
        "partial_fixes": [
            "Terminated 15 idle backend PostgreSQL sessions with pg_terminate_backend()",
            "Temporarily enabled client connection backoff on ingress rate limiter",
        ],
        "worked_fixes": [
            "Increased RDS Postgres max_connections to 400 and tuned HikariCP maximumPoolSize to 65",
            "Applied patch fixing unclosed SQLAlchemy session leak in checkout cart checkout_dao.py",
            "Rolled back deployment commit that set db connection timeout to 1s with non-pooled sessions",
        ],
        "root_cause_summary": "HikariCP connection pool exhausted due to unclosed database connections during peak traffic surge.",
    },
    "redis_eviction": {
        "name": "Redis Eviction Under Flash Sale Traffic",
        "services": ["inventory-svc", "search-svc", "checkout-api"],
        "severities": ["P1", "P2"],
        "alert": {
            "metric": "redis_memory_usage_ratio",
            "threshold": 0.85,
            "value_range": (0.92, 0.99),
            "payload_template": {
                "cluster_node": "redis-shard-03.kartly.internal",
                "maxmemory": "16GB",
                "used_memory": "15.8GB",
                "evicted_keys_per_sec": 4820,
            },
        },
        "log_sources": ["RedisServer", "RedisClient", "CacheManager", "InventoryStockService"],
        "log_messages": [
            ("WARN", "RedisServer", "OOM command not allowed when used memory > 'maxmemory' (policy: volatile-lru)"),
            ("ERROR", "RedisClient", "redis.exceptions.ResponseError: OOM command not allowed when used memory > 'maxmemory'"),
            ("WARN", "CacheManager", "Cache stampede detected for SKU keys; fallback hitting underlying database"),
            ("INFO", "RedisServer", "Evicting 4500 keys per second to maintain memory limits; cache hit ratio dropped to 41%"),
            ("ERROR", "InventoryStockService", "Failed to retrieve stock cache for flash sale event: RedisTimeoutException"),
            ("WARN", "RedisClient", "Connection pool exhausted to redis-cluster: node redis-shard-03 not responding within 2000ms"),
            ("INFO", "CacheManager", "Circuit breaker OPEN for Redis cache tier; routing queries to DB replica"),
        ],
        "failed_fixes": [
            "Restarted redis-server service (caused catastrophic cache stampede on PostgreSQL master)",
            "Doubled service worker concurrency (increased cache read contention further)",
        ],
        "partial_fixes": [
            "Flushed expired ephemeral flash-sale keys using non-blocking SCAN and UNLINK",
            "Temporarily lowered TTL for cart reservation keys from 60 mins to 10 mins",
        ],
        "worked_fixes": [
            "Upgraded ElastiCache cluster instance to r6g.2xlarge (32GB) and configured allkeys-lru eviction policy",
            "Deployed hotfix adding jittered TTL and local memory cache layer (L1 Guava/Cachetools) to eliminate flash sale key evictions",
            "Optimized inventory SKU cache serialization format from raw JSON to MessagePack, cutting memory footprint by 62%",
        ],
        "root_cause_summary": "Redis cluster reached maxmemory limit during flash sale, triggering aggressive key evictions and cache stampede on DB.",
    },
    "tls_expiry": {
        "name": "Expired TLS / mTLS Certificate",
        "services": ["payments-svc", "checkout-api", "delivery-eta-svc"],
        "severities": ["P1", "P2"],
        "alert": {
            "metric": "ingress_tls_cert_expiry_seconds",
            "threshold": 86400,
            "value_range": (0, 3600),
            "payload_template": {
                "domain": "api.kartly.in",
                "secret_name": "ingress-tls-wildcard",
                "cert_issuer": "Let's Encrypt / Vault PKI",
            },
        },
        "log_sources": ["NginxIngress", "EnvoyProxy", "CertManager", "HttpClient"],
        "log_messages": [
            ("ERROR", "NginxIngress", "SSL_do_handshake() failed (SSL: error:0A000086:SSL routines::certificate verify failed)"),
            ("ERROR", "HttpClient", "javax.net.ssl.SSLHandshakeException: PKIX path validation failed: Certificate expired"),
            ("WARN", "CertManager", "Certificate renewal failed for secret 'ingress-tls-wildcard': DNS-01 challenge timed out"),
            ("FATAL", "EnvoyProxy", "downstream TLS error: certificate has expired (notAfter: 2026-10-15T00:00:00Z)"),
            ("ERROR", "payments-svc", "Failed to establish mTLS connection to internal banking gateway: peer certificate expired"),
            ("INFO", "NginxIngress", "Client connection rejected 495 SSL Certificate Error from ip 103.21.244.12"),
        ],
        "failed_fixes": [
            "Restarted Nginx ingress controller without renewing TLS certificate secret",
            "Disabled HTTP/2 protocol in ingress config (did not resolve SSL certificate validation error)",
        ],
        "partial_fixes": [
            "Temporarily switched internal service mesh to permissive mTLS mode",
        ],
        "worked_fixes": [
            "Force-renewed Let's Encrypt wildcard certificate via cert-manager and triggered Envoy secret reload",
            "Rotated expired internal mTLS root CA in HashiCorp Vault and distributed new secrets to payments-svc pods",
            "Fixed broken DNS challenge credentials in cert-manager webhook and re-issued SSL cert",
        ],
        "root_cause_summary": "Automated certificate renewal webhook failed, leading to expired TLS certificate and rejected client handshakes.",
    },
    "payment_timeout": {
        "name": "Third-Party Payment Gateway Timeout",
        "services": ["payments-svc", "checkout-api"],
        "severities": ["P1", "P2"],
        "alert": {
            "metric": "payment_gateway_failure_rate",
            "threshold": 0.05,
            "value_range": (0.25, 0.72),
            "payload_template": {
                "gateway_provider": "Razorpay / PayU",
                "endpoint": "/v1/payments/charge",
                "avg_latency_ms": 12500,
            },
        },
        "log_sources": ["PyRazorpay", "PaymentEngine", "GatewayWebhookHandler", "NginxIngress"],
        "log_messages": [
            ("ERROR", "PyRazorpay", "GatewayTimeoutError: HTTP 504 Gateway Timeout from https://api.razorpay.com/v1/orders/create"),
            ("ERROR", "PaymentEngine", "Payment charge failed for order_id=ord_918241: Request timed out after 10000ms"),
            ("WARN", "GatewayWebhookHandler", "Delayed webhook signature verification for payment_id=pay_88492 (latency=420s)"),
            ("ERROR", "PyRazorpay", "ReadTimeout: HTTPSConnectionPool(host='api.razorpay.com', port=443): Read timed out."),
            ("INFO", "PaymentEngine", "Circuit breaker transitioning to HALF-OPEN for gateway route: PRIMARY_UPI"),
            ("WARN", "checkout-api", "Customer checkout aborted: payment confirmation pending from banking partner"),
        ],
        "failed_fixes": [
            "Increased client HTTP timeout from 10s to 60s (caused cascading thread starvation in payments-svc)",
            "Restarted payment gateway webhook consumer worker (failed because upstream gateway was degraded)",
        ],
        "partial_fixes": [
            "Enabled queued webhook processing in RabbitMQ/Kafka to absorb out-of-order payment notifications",
        ],
        "worked_fixes": [
            "Switched dynamic routing rule to secondary payment gateway (PayU / HDFC Direct) via feature switch",
            "Enabled smart fallback UPI routing and implemented idempotent payment status polling worker",
            "Upstream payment aggregator resolved NPCI UPI switch latency; validated error rates returned to < 0.1%",
        ],
        "root_cause_summary": "Primary payment aggregator experienced upstream NPCI gateway latency, leading to client timeouts and dropped orders.",
    },
    "feature_flag": {
        "name": "Incorrect Feature Flag Configuration",
        "services": ["checkout-api", "search-svc", "inventory-svc", "delivery-eta-svc"],
        "severities": ["P2", "P3"],
        "alert": {
            "metric": "http_5xx_error_rate",
            "threshold": 0.02,
            "value_range": (0.08, 0.35),
            "payload_template": {
                "feature_flag_key": "enable_quick_checkout_v2",
                "rollout_percentage": 100,
                "strategy": "user_id_hash",
            },
        },
        "log_sources": ["FeatureFlagClient", "UnleashSDK", "CheckoutController", "ApplicationRuntime"],
        "log_messages": [
            ("ERROR", "FeatureFlagClient", "JSONDecodeError in feature flag payload 'new_delivery_pricing': unexpected character at line 1 col 42"),
            ("ERROR", "CheckoutController", "NullPointerException: expected non-null config object for variant 'variant_b'"),
            ("WARN", "UnleashSDK", "Failed to parse flag evaluation rules; falling back to default evaluation: True"),
            ("ERROR", "ApplicationRuntime", "Unhandled exception during checkout initialization: AttributeError: 'NoneType' object has no attribute 'discount_rate'"),
            ("INFO", "FeatureFlagClient", "Flag 'enable_quick_checkout_v2' toggled from 10% to 100% by author @rohan.iyer"),
            ("WARN", "CheckoutController", "Legacy checkout flow bypassed but v2 dependencies not initialized in cluster"),
        ],
        "failed_fixes": [
            "Restarted service deployment pods (failed flag config loaded immediately upon pod bootstrap)",
            "Rolled back database schema migrations (unrelated to feature flag toggle state)",
        ],
        "partial_fixes": [
            "Reduced feature flag rollout percentage from 100% to 5% while diagnosing payload syntax",
        ],
        "worked_fixes": [
            "Disabled feature flag 'enable_quick_checkout_v2' in Unleash console, immediately restoring stable v1 flow",
            "Corrected malformed JSON syntax in feature flag payload variant and validated schema with test user cohort",
            "Rolled back flag toggle in configuration repository and redeployed config map",
        ],
        "root_cause_summary": "Feature flag was updated with invalid JSON payload and rolled out to 100% traffic, causing unhandled null exceptions.",
    },
    "disk_full": {
        "name": "Disk Full Caused by Log Rotation Failure",
        "services": ["search-svc", "notification-svc", "delivery-eta-svc"],
        "severities": ["P1", "P2"],
        "alert": {
            "metric": "disk_partition_used_ratio",
            "threshold": 0.85,
            "value_range": (0.96, 1.00),
            "payload_template": {
                "mount_point": "/var/log",
                "filesystem": "/dev/xvda1",
                "free_bytes": 0,
            },
        },
        "log_sources": ["SystemdJournal", "Logrotate", "KafkaBroker", "ElasticsearchNode"],
        "log_messages": [
            ("FATAL", "SystemdJournal", "Failed to write journal log entry: No space left on device"),
            ("ERROR", "Logrotate", "error: logrotate failed for /var/log/kartly/*.log: destination disk full"),
            ("ERROR", "KafkaBroker", "kafka.common.KafkaStorageException: I/O error writing to log segment /var/data/kafka/partition-4"),
            ("WARN", "ElasticsearchNode", "High disk watermark [95%] exceeded on node 'es-data-01', cluster read-only mode activated"),
            ("FATAL", "ApplicationRuntime", "OSError: [Errno 28] No space left on device: '/var/log/application.log'"),
            ("WARN", "SystemdJournal", "Journal stopped dumping core traces due to storage limits"),
        ],
        "failed_fixes": [
            "Restarted application service (application failed to start because it could not open log files)",
            "Increased worker thread pool size (worsened disk write contention)",
        ],
        "partial_fixes": [
            "Manually removed old compressed gz log archives from /tmp and /var/log to free 4GB",
        ],
        "worked_fixes": [
            "Fixed corrupted logrotate cron job configuration, pruned old rotated logs, and resized EBS volume to 200GB",
            "Disabled verbose DEBUG logging level accidentally left enabled in production log4j config and purged 50GB of raw logs",
            "Configured systemd journald SystemMaxUse=5G and set up automated CloudWatch log shipping with S3 lifecycle pruning",
        ],
        "root_cause_summary": "Debug logging accidentally remained enabled after deployment, overflowing /var/log disk partition due to failed logrotate cron.",
    },
    "n_plus_one": {
        "name": "N+1 Query Regression in Relational Queries",
        "services": ["search-svc", "checkout-api", "inventory-svc"],
        "severities": ["P2", "P3"],
        "alert": {
            "metric": "database_cpu_utilization",
            "threshold": 0.80,
            "value_range": (0.88, 0.98),
            "payload_template": {
                "db_instance": "rds-kartly-replica-01",
                "avg_query_count_per_req": 240,
                "p95_db_latency_ms": 3400,
            },
        },
        "log_sources": ["PostgreSQL", "SQLAlchemyLogger", "HibernateProfiler", "CatalogSearchApi"],
        "log_messages": [
            ("WARN", "SQLAlchemyLogger", "High query count detected: 142 SELECT queries executed within single HTTP request context"),
            ("WARN", "PostgreSQL", "Query runtime 4210ms exceeded slow_query_threshold: SELECT * FROM product_variants WHERE product_id = $1"),
            ("INFO", "PostgreSQL", "temporary file: path 'base/pgsql_tmp/pgsql_tmp2819.0', size 18492012 bytes"),
            ("ERROR", "CatalogSearchApi", "Slow search response (p99=4.8s); database CPU throttling under query flood"),
            ("WARN", "HibernateProfiler", "N+1 query anti-pattern: lazy fetching collection 'Product.images' in loop"),
            ("INFO", "PostgreSQL", "pg_stat_statements shows 'SELECT * FROM inventory_items' executed 1,200,000 times/hr"),
        ],
        "failed_fixes": [
            "Scaled application pods horizontally (multiplied the number of N+1 queries hitting the DB)",
            "Restarted PostgreSQL read replica (queries immediately flooded back upon replica availability)",
        ],
        "partial_fixes": [
            "Configured statement-level query caching for frequent product variant lookups",
        ],
        "worked_fixes": [
            "Rewrote query using joinedload/selectinload (eager fetching) and added composite index on (product_id, is_active)",
            "Applied batch fetching patch reducing SQL queries from 250 to 2 per search request, dropping DB CPU from 95% to 18%",
            "Rolled back recent catalog query refactoring commit and deployed eager load configuration",
        ],
        "root_cause_summary": "Recent commit introduced lazy loading in product variant loop, executing 200+ SQL queries per request during search spikes.",
    },
    "kafka_lag": {
        "name": "Kafka Consumer Lag & Partition Rebalance Storm",
        "services": ["notification-svc", "delivery-eta-svc"],
        "severities": ["P2", "P3"],
        "alert": {
            "metric": "kafka_consumer_group_lag_messages",
            "threshold": 10000,
            "value_range": (45000, 220000),
            "payload_template": {
                "consumer_group": "notification-dispatcher-group",
                "topic": "orders.confirmed",
                "partitions_rebalancing": 12,
            },
        },
        "log_sources": ["KafkaConsumer", "NotificationDispatcher", "KafkaBroker", "EventStream"],
        "log_messages": [
            ("WARN", "KafkaConsumer", "Consumer poll timeout exceeded max.poll.interval.ms (300000ms); member removed from group"),
            ("ERROR", "KafkaConsumer", "CommitFailedException: Commit cannot be completed since the group has already rebalanced"),
            ("INFO", "KafkaBroker", "PreparingRebalance (rebalanceId=412): consumer group notification-dispatcher-group rebalancing 24 partitions"),
            ("WARN", "NotificationDispatcher", "Processing lag on topic 'orders.confirmed' partition 8 increased to 85,000 messages"),
            ("ERROR", "EventStream", "SMS gateway rate limit exceeded; messages backing up in notification consumer buffer"),
            ("INFO", "KafkaConsumer", "Partitions revoked: [orders.confirmed-0, orders.confirmed-1, orders.confirmed-2]"),
        ],
        "failed_fixes": [
            "Killed and restarted random consumer pods (triggered endless rebalance storms)",
            "Increased Kafka topic partition count while consumers were frozen (broke consumer assignment)",
        ],
        "partial_fixes": [
            "Temporarily skipped processing of non-critical marketing push notifications",
        ],
        "worked_fixes": [
            "Increased max.poll.interval.ms from 5m to 15m, decreased max.poll.records to 100, and scaled consumer pods from 3 to 12",
            "Fixed downstream SMS provider connection pooling and implemented asynchronous batch dispatch",
            "Reset committed offset to latest for stale promotional messages and isolated transactional notification topic",
        ],
        "root_cause_summary": "Slow downstream SMS provider caused consumer threads to exceed max.poll.interval.ms, triggering continuous rebalance storms.",
    },
}
