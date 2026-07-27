
import datetime
import json
import os

def load_context():
    today = datetime.date.today()
    today_str = today.strftime("%Y-%m-%d")

    # Paths to source files
    notion_bridge_path = f"C:/Users/bot/Desktop/longjiu_system/notion_bridge/{today_str}_strategy_handbook.md"
    snapshot_path = "C:/Users/bot/Desktop/longjiu_system/snapshot.json"
    schedule_events_path = "C:/Users/bot/Desktop/longjiu_system/schedule_events.json"
    output_path = "C:/Users/bot/Desktop/longjiu_system/notion_shared_context.md"

    context_content = []

    # 1. Add Strategic Handbook
    if os.path.exists(notion_bridge_path):
        with open(notion_bridge_path, 'r', encoding='utf-8') as f:
            context_content.append(f"# Strategic Handbook for {today_str}\n")
            context_content.append(f.read())
            context_content.append("\n---\n\n")
    else:
        context_content.append(f"# Strategic Handbook for {today_str} (Not Found)\n\n---\n\n")

    # 2. Add Latest Asset Snapshot
    if os.path.exists(snapshot_path):
        with open(snapshot_path, 'r', encoding='utf-8') as f:
            snapshot_data = json.load(f)
            context_content.append("## Latest Asset Snapshot\n")
            for key, value in snapshot_data.items():
                context_content.append(f"- **{key.replace('_', ' ').title()}**: {value}\n")
            context_content.append("\n---\n\n")
    else:
        context_content.append("## Latest Asset Snapshot (Not Found)\n\n---\n\n")

    # 3. Add Today's Schedule Events
    if os.path.exists(schedule_events_path):
        with open(schedule_events_path, 'r', encoding='utf-8') as f:
            schedule_data = json.load(f)
            today_events = [event for event in schedule_data if event.get("date") == today_str]
            context_content.append(f"## Schedule Events for {today_str}\n")
            if today_events:
                for event in today_events:
                    context_content.append(f"- **{event.get('item')}**: {event.get('amount', '—')} ({event.get('status')})\n")
            else:
                context_content.append("No events scheduled for today.\n")
            context_content.append("\n---\n\n")
    else:
        context_content.append("## Schedule Events (Not Found)\n\n---\n\n")

    # Write to shared context file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(context_content)
    print(f"Notion shared context loaded to {output_path}")

if __name__ == "__main__":
    load_context()
