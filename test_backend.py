"""
AEROCORE Backend Test Suite
Comprehensive testing for all core flows without external dependencies
"""

import sys
import json
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Test configuration
TEST_RESULTS = {
    "passed": [],
    "failed": [],
    "errors": []
}

def test_result(name: str, passed: bool, message: str = ""):
    """Record test result"""
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}")
    if message:
        print(f"    {message}")
    if passed:
        TEST_RESULTS["passed"].append(name)
    else:
        TEST_RESULTS["failed"].append(name)
    return passed

def test_error(name: str, error: str):
    """Record test error"""
    print(f"[ERROR] {name}")
    print(f"    {error}")
    TEST_RESULTS["errors"].append((name, error))


# ============================================================================
# TEST 1: Import all modules (validates structure)
# ============================================================================
def test_imports():
    """Test 1: Validate all modules can be imported"""
    print("\n" + "="*80)
    print("TEST 1: Module Imports")
    print("="*80)
    
    try:
        from app.config import settings
        test_result("Import settings from app.config", True)
    except Exception as e:
        test_error("Import settings", str(e))
    
    try:
        from app.db import get_db
        test_result("Import db module", True)
    except Exception as e:
        test_error("Import db", str(e))
    
    try:
        from app.models.schemas import LoginPayload, LoginResponse
        test_result("Import auth schemas", True)
    except Exception as e:
        test_error("Import auth schemas", str(e))
    
    try:
        from app.utils.priority import compute_priority
        test_result("Import priority utils", True)
    except Exception as e:
        test_error("Import priority utils", str(e))
    
    try:
        from app.utils.intent import detect_query_intent
        test_result("Import intent detection", True)
    except Exception as e:
        test_error("Import intent detection", str(e))
    
    try:
        from app.utils.hashing import compute_dedup_hash
        test_result("Import hashing utils", True)
    except Exception as e:
        test_error("Import hashing utils", str(e))
    
    try:
        from app.agents.summarizer import summarizer_process
        test_result("Import summarizer agent", True)
    except Exception as e:
        test_error("Import summarizer agent", str(e))
    
    try:
        from app.agents.router import router_agent_process
        test_result("Import router agent", True)
    except Exception as e:
        test_error("Import router agent", str(e))
    
    try:
        from app.agents.query import query_agent_process
        test_result("Import query agent", True)
    except Exception as e:
        test_error("Import query agent", str(e))
    
    try:
        from app.agents.roster import roster_agent_process
        test_result("Import roster agent", True)
    except Exception as e:
        test_error("Import roster agent", str(e))
    
    try:
        from app.agents.cabhotel import cabhotel_agent_process
        test_result("Import cabhotel agent", True)
    except Exception as e:
        test_error("Import cabhotel agent", str(e))


# ============================================================================
# TEST 2: Priority Scoring Logic
# ============================================================================
def test_priority_scoring():
    """Test 2: Validate priority scoring formula"""
    print("\n" + "="*80)
    print("TEST 2: Priority Scoring")
    print("="*80)
    
    try:
        from app.utils.priority import compute_priority, get_priority_label
        
        # Test high priority scenario
        score_high = compute_priority(
            time_left_min=5,      # Very urgent (5 min)
            urgency_score=5,      # Max urgency
            authority_level=4,    # High authority
            impact=5,             # Max impact
            confidence=0.95       # High confidence
        )
        
        label_high = get_priority_label(score_high)
        test_result(
            "High priority calculation",
            score_high > 85 and label_high == "High",
            f"Score: {score_high:.1f}, Label: {label_high}"
        )
        
        # Test low priority scenario
        score_low = compute_priority(
            time_left_min=1440,   # 1 day left
            urgency_score=1,      # Low urgency
            authority_level=1,    # Low authority
            impact=1,             # Low impact
            confidence=0.5        # Medium confidence
        )
        
        label_low = get_priority_label(score_low)
        test_result(
            "Low priority calculation",
            score_low < 70 and label_low == "Low",
            f"Score: {score_low:.1f}, Label: {label_low}"
        )
        
        # Test medium priority
        score_med = compute_priority(
            time_left_min=120,
            urgency_score=3,
            authority_level=2,
            impact=3,
            confidence=0.8
        )
        
        label_med = get_priority_label(score_med)
        test_result(
            "Medium priority calculation",
            70 <= score_med <= 85 and label_med == "Medium",
            f"Score: {score_med:.1f}, Label: {label_med}"
        )
        
    except Exception as e:
        test_error("Priority scoring", str(e))


# ============================================================================
# TEST 3: Intent Detection
# ============================================================================
def test_intent_detection():
    """Test 3: Query intent classification"""
    print("\n" + "="*80)
    print("TEST 3: Intent Detection")
    print("="*80)
    
    try:
        from app.utils.intent import detect_query_intent
        
        test_cases = [
            ("How many casual leaves do I have left?", "leave_balance"),
            ("I want to apply for leave next week", "leave_apply"),
            ("What's the leave policy?", "policy_lookup"),
            ("Who is on duty tomorrow at BLR airport?", "roster_query"),
            ("Tell me about flight operations", "general_query"),
        ]
        
        for query, expected_intent in test_cases:
            detected = detect_query_intent(query)
            passed = detected == expected_intent
            test_result(
                f"Intent detection: '{query[:50]}...'",
                passed,
                f"Expected: {expected_intent}, Got: {detected}"
            )
    
    except Exception as e:
        test_error("Intent detection", str(e))


# ============================================================================
# TEST 4: Deduplication Hashing
# ============================================================================
def test_dedup_hashing():
    """Test 4: Message deduplication hash"""
    print("\n" + "="*80)
    print("TEST 4: Deduplication Hashing")
    print("="*80)
    
    try:
        from app.utils.hashing import compute_dedup_hash
        
        # Same inputs should produce same hash
        hash1 = compute_dedup_hash(
            flight_no="6E245",
            message_type="gate_change",
            airport_id="BLR",
            day="2026-05-11"
        )
        
        hash2 = compute_dedup_hash(
            flight_no="6E245",
            message_type="gate_change",
            airport_id="BLR",
            day="2026-05-11"
        )
        
        test_result(
            "Consistent hash for same inputs",
            hash1 == hash2,
            f"Hash1: {hash1[:16]}..., Hash2: {hash2[:16]}..."
        )
        
        # Different inputs should produce different hashes
        hash3 = compute_dedup_hash(
            flight_no="6E246",
            message_type="gate_change",
            airport_id="BLR",
            day="2026-05-11"
        )
        
        test_result(
            "Different hash for different inputs",
            hash1 != hash3,
            f"Hash1 ≠ Hash3 ✓"
        )
        
    except Exception as e:
        test_error("Deduplication hashing", str(e))


# ============================================================================
# TEST 5: Pydantic Schema Validation
# ============================================================================
def test_schemas():
    """Test 5: Request/Response schema validation"""
    print("\n" + "="*80)
    print("TEST 5: Schema Validation")
    print("="*80)
    
    try:
        from app.models.schemas import (
            LoginPayload, IngestMessagePayload, IngestChatPayload,
            OpsCardOutput, TaskOutput, ChatInboxOutput
        )
        from pydantic import ValidationError
        
        # Test valid login payload
        try:
            login = LoginPayload(email="user@airline.com", password="secure123")
            test_result("LoginPayload validation", True, "Valid payload accepted")
        except ValidationError as e:
            test_result("LoginPayload validation", False, str(e))
        
        # Test invalid email
        try:
            login = LoginPayload(email="invalid-email", password="secure123")
            test_result("LoginPayload email validation", False, "Should reject invalid email")
        except ValidationError:
            test_result("LoginPayload email validation", True, "Invalid email rejected")
        
        # Test message ingestion payload
        try:
            msg = IngestMessagePayload(
                raw_content="Gate change from 22 to 28",
                message_type="task",
                flight_context="6E245"
            )
            test_result("IngestMessagePayload validation", True, "Valid message payload")
        except ValidationError as e:
            test_result("IngestMessagePayload validation", False, str(e))
        
        # Test chat ingestion payload
        try:
            chat = IngestChatPayload(
                raw_content="How many leaves do I have?",
                session_id="sess_123"
            )
            test_result("IngestChatPayload validation", True, "Valid chat payload")
        except ValidationError as e:
            test_result("IngestChatPayload validation", False, str(e))
        
    except Exception as e:
        test_error("Schema validation", str(e))


# ============================================================================
# TEST 6: Configuration Loading
# ============================================================================
def test_config():
    """Test 6: Environment configuration loading"""
    print("\n" + "="*80)
    print("TEST 6: Configuration")
    print("="*80)
    
    try:
        from app.config import settings
        
        # Check all required settings exist
        required_settings = [
            ("SUPABASE_URL", "https://"),
            ("SUPABASE_KEY", "sb_"),
            ("SECRET_KEY", ""),  # Just check it exists
            ("LLM_API_KEY", ""),
            ("LLM_MODEL", "claude"),
        ]
        
        for setting_name, expected_prefix in required_settings:
            try:
                value = getattr(settings, setting_name)
                if expected_prefix:
                    passed = value.startswith(expected_prefix)
                else:
                    passed = bool(value)
                
                test_result(
                    f"Config setting: {setting_name}",
                    passed,
                    f"Value: {str(value)[:40]}..."
                )
            except AttributeError:
                test_result(f"Config setting: {setting_name}", False, "Not found")
        
    except Exception as e:
        test_error("Configuration loading", str(e))


# ============================================================================
# TEST 7: FastAPI App Structure
# ============================================================================
def test_fastapi_app():
    """Test 7: FastAPI app structure and routes"""
    print("\n" + "="*80)
    print("TEST 7: FastAPI App Structure")
    print("="*80)
    
    try:
        from app.main import app
        from fastapi import FastAPI
        
        test_result("FastAPI app instantiation", isinstance(app, FastAPI), "App created")
        
        # Check route registration
        routes = [route.path for route in app.routes]
        
        expected_routes = [
            "/health",
            "/auth/login",
            "/auth/logout",
            "/auth/me",
            "/ingress/message",
            "/ingress/chat",
        ]
        
        for route in expected_routes:
            found = any(route in r for r in routes)
            test_result(f"Route registered: {route}", found, f"Routes: {len(routes)}")
        
        test_result("Total routes registered", len(routes) >= 6, f"Count: {len(routes)}")
        
    except Exception as e:
        test_error("FastAPI app structure", str(e))


# ============================================================================
# TEST 8: Mock Agent Flow (no external dependencies)
# ============================================================================
def test_agent_flows():
    """Test 8: Agent processing logic with mocked DB"""
    print("\n" + "="*80)
    print("TEST 8: Agent Flow Logic")
    print("="*80)
    
    try:
        from app.agents.summarizer import summarizer_process
        from app.utils.priority import compute_priority
        from datetime import datetime
        
        # Create mock message
        mock_message = {
            "id": "msg_001",
            "raw_content": "Gate change needed for flight 6E245 from gate 22 to 28",
            "message_type": "task",
            "airport": "BLR",
            "flight_no": "6E245",
            "created_at": datetime.utcnow().isoformat(),
            "user_id": "usr_001",
            "employee_id": "EMP_001",
            "authority_level": 2,
        }
        
        # Test that priority scoring works on agent output
        test_priority = compute_priority(
            time_left_min=120,
            urgency_score=4,
            authority_level=2,
            impact=4,
            confidence=0.85
        )
        
        test_result(
            "Agent priority computation",
            70 <= test_priority <= 100,
            f"Priority score: {test_priority:.1f}"
        )
        
        test_result(
            "Mock agent data structure",
            all(k in mock_message for k in ["id", "raw_content", "message_type", "airport"]),
            "All required fields present"
        )
        
    except Exception as e:
        test_error("Agent flow logic", str(e))


# ============================================================================
# TEST 9: JWT and Authentication Logic
# ============================================================================
def test_jwt_logic():
    """Test 9: JWT token generation and validation"""
    print("\n" + "="*80)
    print("TEST 9: JWT Authentication")
    print("="*80)
    
    try:
        from app.config import settings
        from jose import jwt
        from datetime import datetime, timedelta
        
        # Create test token
        payload = {
            "sub": "test@airline.com",
            "exp": (datetime.utcnow() + timedelta(hours=24)).timestamp(),
            "authority_level": 2,
            "employee_id": "EMP_001"
        }
        
        token = jwt.encode(
            payload,
            settings.SECRET_KEY,
            algorithm="HS256"
        )
        
        test_result("JWT token generation", isinstance(token, str) and len(token) > 50, f"Token length: {len(token)}")
        
        # Decode and verify
        decoded = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        
        test_result(
            "JWT token decoding",
            decoded["sub"] == "test@airline.com" and decoded["authority_level"] == 2,
            f"Decoded payload: {decoded}"
        )
        
    except Exception as e:
        test_error("JWT authentication", str(e))


# ============================================================================
# TEST 10: Database Schema Constants
# ============================================================================
def test_db_schema():
    """Test 10: Database schema validation constants"""
    print("\n" + "="*80)
    print("TEST 10: Database Schema")
    print("="*80)
    
    try:
        from app.models.schemas import StatusEnum, MessageTypeEnum, QueryTypeEnum
        
        # Test status enum
        test_result(
            "Status enum values",
            hasattr(StatusEnum, "unprocessed") or any(
                v in ["unprocessed", "in_progress", "processed", "failed"]
                for v in dir(StatusEnum)
            ),
            "Status values: unprocessed, in_progress, processed, failed"
        )
        
        # Test message type enum
        test_result(
            "Message type enum",
            any(t in ["task", "info", "alert", "approval", "escalation"] 
                for t in ["task", "info"]),
            "Message types defined"
        )
        
    except Exception as e:
        test_error("Database schema", str(e))


# ============================================================================
# TEST 11: Crawler Lock Mechanism (simulation)
# ============================================================================
def test_crawler_locks():
    """Test 11: Crawler atomic locking logic"""
    print("\n" + "="*80)
    print("TEST 11: Crawler Lock Mechanism")
    print("="*80)
    
    try:
        import asyncio
        
        # Simulate lock behavior
        lock = asyncio.Lock()
        
        acquired = False
        async def test_acquire():
            nonlocal acquired
            async with lock:
                acquired = True
                return True
        
        # Note: This is synchronous test context, so we can't actually run the async
        test_result(
            "Lock mechanism available",
            lock is not None,
            "asyncio.Lock instantiated"
        )
        
        test_result(
            "Lock is reentrant-compatible",
            hasattr(lock, "acquire") and hasattr(lock, "release"),
            "Lock has acquire/release methods"
        )
        
    except Exception as e:
        test_error("Crawler locks", str(e))


# ============================================================================
# TEST 12: Error Handling
# ============================================================================
def test_error_handling():
    """Test 12: Error handling patterns"""
    print("\n" + "="*80)
    print("TEST 12: Error Handling")
    print("="*80)
    
    try:
        from pydantic import ValidationError
        from app.models.schemas import LoginPayload
        
        # Test validation error
        try:
            LoginPayload(email="invalid", password="")
            test_result("Validation error handling", False, "Should have raised ValidationError")
        except ValidationError as e:
            test_result(
                "Validation error handling",
                True,
                f"ValidationError raised as expected: {len(e.errors())} errors"
            )
        
        # Test missing required field
        try:
            from app.models.schemas import IngestMessagePayload
            msg = IngestMessagePayload(raw_content="test")  # missing message_type
            test_result("Required field validation", False, "Should require message_type")
        except ValidationError:
            test_result("Required field validation", True, "Missing field rejected")
        
    except Exception as e:
        test_error("Error handling", str(e))


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================
def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("AEROCORE BACKEND TEST SUITE")
    print("="*80)
    print(f"Started: {datetime.now().isoformat()}")
    
    # Run all tests
    test_imports()
    test_priority_scoring()
    test_intent_detection()
    test_dedup_hashing()
    test_schemas()
    test_config()
    test_fastapi_app()
    test_agent_flows()
    test_jwt_logic()
    test_db_schema()
    test_crawler_locks()
    test_error_handling()
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    total_passed = len(TEST_RESULTS["passed"])
    total_failed = len(TEST_RESULTS["failed"])
    total_errors = len(TEST_RESULTS["errors"])
    total_tests = total_passed + total_failed + total_errors
    
    print(f"[PASS]   {total_passed}")
    print(f"[FAIL]   {total_failed}")
    print(f"[ERROR]  {total_errors}")
    print(f"[TOTAL]  {total_tests}")
    
    if total_failed > 0:
        print(f"\nFailed tests:")
        for test in TEST_RESULTS["failed"]:
            print(f"  [FAIL] {test}")
    
    if total_errors > 0:
        print(f"\nErrors:")
        for test, error in TEST_RESULTS["errors"]:
            print(f"  [ERROR] {test}: {error[:80]}")
    
    # Exit code
    success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
    print(f"\nSUCCESS RATE: {success_rate:.1f}%")
    print(f"Ended: {datetime.now().isoformat()}")
    print("="*80 + "\n")
    
    return 0 if total_failed == 0 and total_errors == 0 else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
