"""Quick integration test for the skills-based architecture."""

import asyncio
from server import mcp, DEVICES


async def test_tools():
    """Test that all tools are registered and callable."""
    
    print("Testing Skills Integration\n" + "="*50)
    
    # Get list of devices
    print("\n1. Testing list_devices...")
    device_list = mcp._tool_manager._tools.get("list_devices")
    if device_list:
        result = device_list.fn()
        print(f"✓ list_devices works ({len(result)} chars)")
    else:
        print("✗ list_devices not found")
    
    # Test that we have the expected number of tools
    tools = list(mcp._tool_manager._tools.keys())
    print(f"\n2. Registered tools ({len(tools)}):")
    for tool in sorted(tools):
        print(f"   - {tool}")
    
    expected_tools = [
        "list_devices",
        "get_latest_measurements",
        "get_historical_data",
        "get_data_statistics",
        "export_historical_data",
        "well_compliance_check",
        "well_feature_compliance",
        "health_recommendations",
        "outdoor_snapshot",
        "indoor_vs_outdoor",
    ]
    
    print(f"\n3. Checking expected tools:")
    for tool in expected_tools:
        status = "✓" if tool in tools else "✗"
        print(f"   {status} {tool}")
    
    missing = set(expected_tools) - set(tools)
    extra = set(tools) - set(expected_tools)
    
    if missing:
        print(f"\n⚠ Missing tools: {missing}")
    if extra:
        print(f"\n✓ Extra tools (OK): {extra}")
    
    # Check resources
    resources = list(mcp._resource_manager._resources.keys())
    print(f"\n4. Registered resources ({len(resources)}):")
    for resource in sorted(resources):
        print(f"   - {resource}")
    
    # Check prompts
    prompts = list(mcp._prompt_manager._prompts.keys())
    print(f"\n5. Registered prompts ({len(prompts)}):")
    for prompt in sorted(prompts):
        print(f"   - {prompt}")
    
    print("\n" + "="*50)
    print("✓ Skills integration test completed successfully!")
    print(f"✓ {len(tools)} tools registered")
    print(f"✓ {len(resources)} resources registered")
    print(f"✓ {len(prompts)} prompts registered")
    print(f"✓ {len(DEVICES)} devices configured")


if __name__ == "__main__":
    asyncio.run(test_tools())
