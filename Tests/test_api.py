"""
Test FastAPI Routes
Author: Roshan
Purpose: Automated API test suite for TechAdmin endpoints
"""

import pytest
from fastapi.testclient import TestClient
from App.main import app

client = TestClient(app)


def test_health_check():
    """
    Test 1: Verify health check endpoint returns 200 OK and healthy status.
    """
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "TechAdmin Agent Platform"


def test_intents():
    """
    Test 2: Verify supported intents endpoint returns 200 OK and intent list.
    """
    response = client.get("/api/v1/intents")
    assert response.status_code == 200
    data = response.json()
    assert "intents" in data
    assert len(data["intents"]) > 0


def test_request_submission():
    """
    Test 3: Verify valid request submission executes successfully.
    """
    payload = {
        "user_input": "Reset password for user aman.gupta",
        "request_id": "test_req_001"
    }
    response = client.post("/api/v1/request", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "request_id" in data
    assert data["request_id"] == "test_req_001"
    assert "message" in data


def test_invalid_request():
    """
    Test 4: Verify empty input is rejected by Pydantic with 422 Unprocessable Entity.
    """
    payload = {
        "user_input": ""
    }
    response = client.post("/api/v1/request", json=payload)
    assert response.status_code == 422
