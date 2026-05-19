import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.agent import run_agent

result = run_agent(
    session_history=[],
    message="Find the senescent cells in this dataset",
    file_id="test-kidney-001",
    species="mouse"
)

print("Reply:", result["reply"])
print("Tools called:", [t["name"] for t in result["tool_calls"]])

# Add to test_agent.py
result2 = run_agent(
    session_history=[],
    message="How do kidney cells change between young and old mice?",
    file_id="test-kidney-001",
    species="mouse"
)
print("\nTest 2 Reply:", result2["reply"])
print("Tools called:", [t["name"] for t in result2["tool_calls"]])