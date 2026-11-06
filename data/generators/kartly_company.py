"""
RecallOps - Kartly Fictional Company Definition
Member 3: Database & Data Engineering

Defines Kartly's 6 core services and 8 Indian engineers.
"""

from typing import Any, Dict, List

ENGINEERS_DATA: List[Dict[str, Any]] = [
    {
        "id": 1,
        "name": "Aarav Sharma",
        "team": "Platform SRE",
        "slack_handle": "@aarav.sharma",
    },
    {
        "id": 2,
        "name": "Priya Patel",
        "team": "Payments Engineering",
        "slack_handle": "@priya.patel",
    },
    {
        "id": 3,
        "name": "Rohan Iyer",
        "team": "Checkout Engineering",
        "slack_handle": "@rohan.iyer",
    },
    {
        "id": 4,
        "name": "Ananya Rao",
        "team": "Inventory & Logistics",
        "slack_handle": "@ananya.rao",
    },
    {
        "id": 5,
        "name": "Vikram Malhotra",
        "team": "Search & Catalog",
        "slack_handle": "@vikram.m",
    },
    {
        "id": 6,
        "name": "Neha Deshmukh",
        "team": "Platform Infrastructure",
        "slack_handle": "@neha.d",
    },
    {
        "id": 7,
        "name": "Aditya Verma",
        "team": "Notifications & Messaging",
        "slack_handle": "@aditya.v",
    },
    {
        "id": 8,
        "name": "Sneha Nair",
        "team": "Fulfillment & ETA",
        "slack_handle": "@sneha.n",
    },
]

SERVICES_DATA: List[Dict[str, Any]] = [
    {
        "id": 1,
        "name": "checkout-api",
        "team": "Checkout Engineering",
        "owner_id": 3,  # Rohan Iyer
        "tier": "Tier-1",
    },
    {
        "id": 2,
        "name": "payments-svc",
        "team": "Payments Engineering",
        "owner_id": 2,  # Priya Patel
        "tier": "Tier-1",
    },
    {
        "id": 3,
        "name": "inventory-svc",
        "team": "Inventory & Logistics",
        "owner_id": 4,  # Ananya Rao
        "tier": "Tier-1",
    },
    {
        "id": 4,
        "name": "search-svc",
        "team": "Search & Catalog",
        "owner_id": 5,  # Vikram Malhotra
        "tier": "Tier-2",
    },
    {
        "id": 5,
        "name": "notification-svc",
        "team": "Notifications & Messaging",
        "owner_id": 7,  # Aditya Verma
        "tier": "Tier-2",
    },
    {
        "id": 6,
        "name": "delivery-eta-svc",
        "team": "Fulfillment & ETA",
        "owner_id": 8,  # Sneha Nair
        "tier": "Tier-2",
    },
]
