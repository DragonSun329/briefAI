"""
WebSocket Streaming Examples for briefAI Python SDK

Real-time data streaming for signal updates, divergence alerts, and events.
"""

import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

# Import the SDK
import sys
sys.path.insert(0, "..")
from briefai_client import BriefAIClient, create_client


def example_basic_streaming():
    """
    Example: Basic real-time streaming.
    
    Subscribe to all updates and print them as they arrive.
    """
    client = create_client(api_key="your_api_key")
    
    print("Connecting to WebSocket feed...")
    print("Press Ctrl+C to stop\n")
    
    try:
        for update in client.stream.subscribe(all_updates=True):
            timestamp = datetime.fromisoformat(update.get("timestamp", "").replace("Z", "+00:00"))
            msg_type = update.get("type", "unknown")
            
            print(f"[{timestamp.strftime('%H:%M:%S')}] {msg_type}:")
            
            if msg_type == "signal_update":
                print(f"  Entity: {update.get('entity_id')}")
                print(f"  Category: {update.get('category')}")
                print(f"  Score: {update.get('data', {}).get('score', 'N/A')}")
            
            elif msg_type == "divergence_alert":
                print(f"  Entity: {update.get('entity_name')}")
                print(f"  Severity: {update.get('severity', 'N/A')}")
                data = update.get("data", {})
                print(f"  Type: {data.get('divergence_type', 'N/A')}")
            
            elif msg_type == "event":
                print(f"  Event Type: {update.get('event_type')}")
                print(f"  Entity: {update.get('entity_id')}")
            
            print()
    
    except KeyboardInterrupt:
        print("\nStopping stream...")
        client.stream.close()


def example_entity_tracking():
    """
    Example: Track specific entities in real-time.
    
    Subscribe to updates for OpenAI, Anthropic, and Google DeepMind.
    """
    client = create_client(api_key="your_api_key")
    
    tracked_entities = ["openai", "anthropic", "deepmind"]
    
    print(f"Tracking entities: {', '.join(tracked_entities)}")
    print("Press Ctrl+C to stop\n")
    
    # Track entity scores
    entity_scores: Dict[str, Dict[str, float]] = {e: {} for e in tracked_entities}
    
    try:
        for update in client.stream.subscribe(entities=tracked_entities):
            if update.get("type") == "signal_update":
                entity_id = update.get("entity_id")
                category = update.get("category")
                score = update.get("data", {}).get("score")
                
                if entity_id in entity_scores and score is not None:
                    old_score = entity_scores[entity_id].get(category)
                    entity_scores[entity_id][category] = score
                    
                    # Alert on significant changes
                    if old_score and abs(score - old_score) > 5:
                        change = score - old_score
                        emoji = "📈" if change > 0 else "📉"
                        print(f"{emoji} {entity_id} {category}: {old_score:.1f} → {score:.1f} ({change:+.1f})")
    
    except KeyboardInterrupt:
        print("\nFinal scores:")
        for entity, scores in entity_scores.items():
            print(f"\n{entity}:")
            for cat, score in scores.items():
                print(f"  {cat}: {score:.1f}")
        
        client.stream.close()


def example_divergence_alerts():
    """
    Example: Real-time divergence alert handler.
    
    Subscribe only to divergence alerts and take action.
    """
    client = create_client(api_key="your_api_key")
    
    print("Listening for divergence alerts...")
    print("Press Ctrl+C to stop\n")
    
    alert_count = 0
    opportunities: List[Dict[str, Any]] = []
    risks: List[Dict[str, Any]] = []
    
    try:
        for update in client.stream.subscribe(divergences=True):
            if update.get("type") != "divergence_alert":
                continue
            
            alert_count += 1
            data = update.get("data", {})
            
            entity = update.get("entity_name", "Unknown")
            interpretation = data.get("interpretation", "unknown")
            magnitude = data.get("divergence_magnitude", 0)
            confidence = data.get("confidence", 0)
            
            # Categorize
            alert_info = {
                "entity": entity,
                "magnitude": magnitude,
                "confidence": confidence,
                "timestamp": update.get("timestamp"),
                "high_category": data.get("high_signal_category"),
                "low_category": data.get("low_signal_category"),
            }
            
            if interpretation == "opportunity":
                opportunities.append(alert_info)
                emoji = "🟢"
            elif interpretation == "risk":
                risks.append(alert_info)
                emoji = "🔴"
            else:
                emoji = "🟡"
            
            # Print alert
            severity = update.get("severity", "medium")
            print(f"{emoji} [{severity.upper()}] {entity}")
            print(f"   Interpretation: {interpretation}")
            print(f"   High: {data.get('high_signal_category')} ({data.get('high_signal_score', 0):.1f})")
            print(f"   Low: {data.get('low_signal_category')} ({data.get('low_signal_score', 0):.1f})")
            print(f"   Magnitude: {magnitude:.1f}, Confidence: {confidence:.0%}")
            print()
    
    except KeyboardInterrupt:
        print(f"\n{'='*50}")
        print(f"Summary: {alert_count} alerts received")
        print(f"  Opportunities: {len(opportunities)}")
        print(f"  Risks: {len(risks)}")
        
        if opportunities:
            print("\nTop Opportunities:")
            for opp in sorted(opportunities, key=lambda x: x["magnitude"], reverse=True)[:3]:
                print(f"  - {opp['entity']}: magnitude {opp['magnitude']:.1f}")
        
        if risks:
            print("\nTop Risks:")
            for risk in sorted(risks, key=lambda x: x["magnitude"], reverse=True)[:3]:
                print(f"  - {risk['entity']}: magnitude {risk['magnitude']:.1f}")
        
        client.stream.close()


def example_category_monitoring():
    """
    Example: Monitor specific signal categories.
    
    Track technical and financial signals separately.
    """
    client = create_client(api_key="your_api_key")
    
    print("Monitoring technical and financial signals...")
    print("Press Ctrl+C to stop\n")
    
    category_stats = {
        "technical": {"updates": 0, "avg_score": 0, "scores": []},
        "financial": {"updates": 0, "avg_score": 0, "scores": []},
    }
    
    try:
        for update in client.stream.subscribe(categories=["technical", "financial"]):
            if update.get("type") != "signal_update":
                continue
            
            category = update.get("category")
            score = update.get("data", {}).get("score")
            
            if category in category_stats and score is not None:
                stats = category_stats[category]
                stats["updates"] += 1
                stats["scores"].append(score)
                stats["avg_score"] = sum(stats["scores"]) / len(stats["scores"])
                
                # Print every 10th update
                if stats["updates"] % 10 == 0:
                    print(f"[{category}] {stats['updates']} updates, avg: {stats['avg_score']:.1f}")
    
    except KeyboardInterrupt:
        print("\nFinal Statistics:")
        for cat, stats in category_stats.items():
            if stats["scores"]:
                min_score = min(stats["scores"])
                max_score = max(stats["scores"])
                print(f"\n{cat}:")
                print(f"  Total updates: {stats['updates']}")
                print(f"  Average score: {stats['avg_score']:.1f}")
                print(f"  Range: {min_score:.1f} - {max_score:.1f}")
        
        client.stream.close()


def example_with_batching():
    """
    Example: Use message batching for high-throughput (Premium).
    
    Configure the connection for batched message delivery.
    """
    import websocket
    import json
    
    api_key = "your_premium_api_key"
    base_url = "ws://localhost:8000/ws"
    
    print("Connecting with batching enabled...")
    
    ws = websocket.create_connection(f"{base_url}?api_key={api_key}")
    
    # Wait for connection
    initial = json.loads(ws.recv())
    print(f"Connected: {initial.get('type')}")
    
    # Configure batching
    ws.send(json.dumps({
        "type": "configure",
        "batch_enabled": True,
        "batch_size": 10,
        "batch_interval_ms": 1000
    }))
    
    config_ack = json.loads(ws.recv())
    print(f"Batching configured: {config_ack}")
    
    # Subscribe
    ws.send(json.dumps({"type": "subscribe", "subscription_type": "all"}))
    
    try:
        message_count = 0
        batch_count = 0
        
        while True:
            data = ws.recv()
            msg = json.loads(data)
            
            if msg.get("type") == "batch":
                batch_count += 1
                batch_messages = msg.get("messages", [])
                message_count += len(batch_messages)
                print(f"Batch #{batch_count}: {len(batch_messages)} messages (total: {message_count})")
            elif msg.get("type") == "heartbeat":
                ws.send(json.dumps({"type": "ping"}))
            elif msg.get("type") not in ("pong", "subscribed", "config_ack"):
                message_count += 1
                print(f"Single message: {msg.get('type')}")
    
    except KeyboardInterrupt:
        print(f"\nTotal batches: {batch_count}, Total messages: {message_count}")
        ws.close()


def example_reconnection_handling():
    """
    Example: Handle disconnections and reconnect automatically.
    
    Maintains subscriptions across reconnections.
    """
    import websocket
    import json
    import time
    
    api_key = "your_api_key"
    base_url = "ws://localhost:8000/ws"
    
    connection_id: Optional[str] = None
    subscriptions = [
        {"type": "subscribe", "subscription_type": "entity", "target": "openai"},
        {"type": "subscribe", "subscription_type": "divergence"},
    ]
    
    def connect():
        nonlocal connection_id
        
        url = f"{base_url}?api_key={api_key}"
        if connection_id:
            url += f"&reconnect_id={connection_id}"
        
        ws = websocket.create_connection(url)
        
        # Get connection info
        initial = json.loads(ws.recv())
        connection_id = initial.get("connection_id")
        is_reconnect = initial.get("type") == "reconnected"
        
        print(f"{'Reconnected' if is_reconnect else 'Connected'}: {connection_id}")
        
        # Resubscribe
        for sub in subscriptions:
            ws.send(json.dumps(sub))
            json.loads(ws.recv())  # Consume confirmation
        
        print(f"Subscribed to {len(subscriptions)} feeds")
        
        return ws
    
    reconnect_delay = 1
    max_delay = 60
    
    while True:
        try:
            ws = connect()
            reconnect_delay = 1  # Reset delay on successful connection
            
            while True:
                data = ws.recv()
                msg = json.loads(data)
                
                if msg.get("type") == "heartbeat":
                    ws.send(json.dumps({"type": "ping"}))
                elif msg.get("type") not in ("pong", "subscribed"):
                    print(f"Update: {msg.get('type')} - {msg.get('entity_id', '')}")
        
        except websocket.WebSocketConnectionClosedException:
            print(f"Connection lost. Reconnecting in {reconnect_delay}s...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_delay)
        
        except KeyboardInterrupt:
            print("\nStopping...")
            break
        
        except Exception as e:
            print(f"Error: {e}. Reconnecting in {reconnect_delay}s...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_delay)


def main():
    """Run streaming examples."""
    print("=" * 60)
    print("briefAI WebSocket Streaming Examples")
    print("=" * 60)
    print("""
Choose an example to run:
1. Basic streaming (all updates)
2. Entity tracking (OpenAI, Anthropic, DeepMind)
3. Divergence alerts
4. Category monitoring
5. Batching (Premium)
6. Reconnection handling

Enter your choice (1-6): """, end="")
    
    # Uncomment to run interactively:
    # choice = input().strip()
    # examples = {
    #     "1": example_basic_streaming,
    #     "2": example_entity_tracking,
    #     "3": example_divergence_alerts,
    #     "4": example_category_monitoring,
    #     "5": example_with_batching,
    #     "6": example_reconnection_handling,
    # }
    # if choice in examples:
    #     examples[choice]()
    # else:
    #     print("Invalid choice")
    
    print("\nTo run examples, uncomment the code and provide your API key.")


if __name__ == "__main__":
    main()
