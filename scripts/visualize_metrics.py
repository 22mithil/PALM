import os
import json
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from math import pi

# Configure plotting style
sns.set_theme(style="whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)

def load_evaluation_data(base_path: str):
    """Parses all JSON session reports from the synthetic evaluations folder."""
    session_data_list = []
    bottleneck_data_list = []
    turn_data_list = []
    raw_sessions = []
    
    # Pre-load all full_session.json files into a dictionary keyed by session_id
    session_turns_map = {}
    full_session_pattern = os.path.join(base_path, "evaluations", "sessions", "synthetic", "**", "full_session.json")
    for fpath in glob.glob(full_session_pattern, recursive=True):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                turns = json.load(f)
                if turns and len(turns) > 0:
                    sid = turns[0].get("session_id")
                    if sid:
                        session_turns_map[sid] = turns
        except Exception as e:
            print(f"Failed to load turn data from {fpath}: {e}")
            
    # Search for all json files in the synthetic reports directories
    search_pattern = os.path.join(base_path, "evaluations", "reports", "synthetic", "**", "*.json")
    for filepath in glob.glob(search_pattern, recursive=True):
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                raw_sessions.append(data)
                persona = data.get("persona", "unknown")
                
                # Flatten the main session metrics
                flat_data = {
                    "session_id": data.get("session_id"),
                    "persona": persona,
                    "total_turns": data.get("total_turns"),
                    "latency_avg_ms": data.get("latency_avg_ms"),
                    "token_total": data.get("token_consumption", {}).get("total_tokens", 0),
                    "avg_tokens_per_turn": data.get("token_consumption", {}).get("avg_tokens_per_turn", 0),
                    "final_completion_percent": data.get("final_completion_percent", 0),
                    "affective_volatility": data.get("affective_volatility", 0),
                    "intervention_success_rate": data.get("intervention_success_rate", 0.0),
                    "student_tutor_talk_ratio": data.get("student_tutor_talk_ratio", 0.0),
                    "time_to_boredom_turn": data.get("time_to_boredom_turn"),
                    "gaze_away_percentage": data.get("gaze_away_percentage", 0.0),
                    "avg_adoption_delay_turns": data.get("vocabulary_adoption", {}).get("avg_adoption_delay_turns", 0.0)
                }
                
                emotion_dist = data.get("emotion_distribution", {})
                flat_data["emotion_sad"] = emotion_dist.get("sad", {}).get("percent", 0)
                flat_data["emotion_frustrated"] = emotion_dist.get("frustrated", {}).get("percent", 0)
                flat_data["emotion_confused"] = emotion_dist.get("confused", {}).get("percent", 0)
                flat_data["emotion_neutral"] = emotion_dist.get("neutral", {}).get("percent", 0)
                flat_data["emotion_happy"] = emotion_dist.get("happy", {}).get("percent", 0)
                flat_data["emotion_confident"] = emotion_dist.get("confident", {}).get("percent", 0)
                
                # Hint Exhaustion 
                hints = data.get("hint_exhaustion_rate", {})
                flat_data["turns_with_hints"] = hints.get("turns_with_hints", 0)
                flat_data["turns_at_max_hints"] = hints.get("turns_at_max_hints", 0)
                
                # Extract LLM Judge scores
                judge_scores = data.get("llm_judge_scores", {})
                for metric in [
                    "socratic_adherence", "empathy_validation", "age_appropriate_tone",
                    "guardrail_resilience", "curriculum_grounding", "faithfulness",
                    "answer_relevance", "concept_leakage", "hint_progression_compliance",
                    "tone_consistency", "off_topic_deflection", "prompt_injection_resilience"
                ]:
                    if metric in judge_scores and isinstance(judge_scores[metric], dict):
                        flat_data[f"judge_{metric}"] = judge_scores[metric].get("score", 0)
                
                session_data_list.append(flat_data)
                
                # Extract section bottlenecks into a separate table for stacked bar charts
                for b in data.get("section_bottlenecks", []):
                    bottleneck_data_list.append({
                        "session_id": data.get("session_id"),
                        "persona": persona,
                        "section_id": b.get("section_id"),
                        "turns_spent": b.get("turns_spent", 0),
                        "is_bottleneck": b.get("is_bottleneck", False)
                    })
                    
                # Extract turn-level latencies and agent sequences
                if flat_data["session_id"] in session_turns_map:
                    turns = session_turns_map[flat_data["session_id"]]
                    for turn in turns:
                        agents = turn.get("agents_fired", [])
                        primary_agent = agents[0] if agents else "unknown"
                        turn_data_list.append({
                            "session_id": flat_data["session_id"],
                            "persona": persona,
                            "turn_count": turn.get("turn_count", 0),
                            "pipeline_latency_ms": turn.get("pipeline_latency_ms", 0),
                            "primary_agent": primary_agent
                        })
                    
            except json.JSONDecodeError:
                print(f"Failed to parse JSON: {filepath}")
                
    return pd.DataFrame(session_data_list), pd.DataFrame(bottleneck_data_list), pd.DataFrame(turn_data_list), raw_sessions

# ═══════════════════════════════════════════════════════════════
# AGGREGATED VISUALIZATIONS (Across all sessions)
# ═══════════════════════════════════════════════════════════════

def plot_aggregated_radar_chart(df: pd.DataFrame, output_dir: str):
    """Generates a radar/spider chart of qualitative metrics grouped by persona."""
    judge_cols = [c for c in df.columns if c.startswith('judge_')]
    if not judge_cols: return
        
    grouped = df.groupby('persona')[judge_cols].mean().reset_index()
    categories = [c.replace('judge_', '').replace('_', ' ').title() for c in judge_cols]
    N = len(categories)
    
    angles = [n / float(N) * 2 * pi for n in range(N)]
    angles += angles[:1]
    
    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    
    for i, row in grouped.iterrows():
        values = row[judge_cols].values.flatten().tolist()
        values += values[:1]
        ax.plot(angles, values, linewidth=2, linestyle='solid', label=row['persona'])
        ax.fill(angles, values, alpha=0.1)
        
    plt.xticks(angles[:-1], categories, size=10)
    ax.set_ylim(0, 10)
    plt.title('Qualitative Metrics by Persona (LLM-as-a-Judge)', size=15, y=1.1)
    plt.legend(loc='upper right', bbox_to_anchor=(0.1, 0.1))
    plt.savefig(os.path.join(output_dir, "aggregated_radar_chart.png"), bbox_inches='tight')
    plt.close()

def plot_heatmap_metrics(df: pd.DataFrame, output_dir: str):
    judge_cols = [c for c in df.columns if c.startswith('judge_')]
    if not judge_cols: return
        
    grouped = df.groupby('persona')[judge_cols].mean()
    grouped.columns = [c.replace('judge_', '').replace('_', ' ').title() for c in grouped.columns]
    
    plt.figure(figsize=(12, 6))
    sns.heatmap(grouped, annot=True, cmap="YlGnBu", vmin=0, vmax=10)
    plt.title('Average Qualitative Scores by Persona', fontsize=14)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_heatmap_qualitative.png"))
    plt.close()

def plot_latency_boxplot(df: pd.DataFrame, output_dir: str):
    if 'latency_avg_ms' not in df.columns: return
    plt.figure(figsize=(10, 6))
    sns.boxplot(x='persona', y='latency_avg_ms', data=df)
    plt.title('Average Latency Distribution by Persona', fontsize=14)
    plt.ylabel('Latency (ms)')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_boxplot_latency.png"))
    plt.close()

def plot_token_cost_bar(df: pd.DataFrame, output_dir: str):
    if 'token_total' not in df.columns: return
    plt.figure(figsize=(10, 6))
    sns.barplot(x='persona', y='token_total', data=df, errorbar=None)
    plt.title('Total Token Consumption per Persona', fontsize=14)
    plt.ylabel('Total Tokens')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_barplot_tokens.png"))
    plt.close()

def plot_learning_efficacy_scatter(df: pd.DataFrame, output_dir: str):
    if 'judge_empathy_validation' not in df.columns or 'final_completion_percent' not in df.columns:
        return
    plt.figure(figsize=(10, 6))
    sns.scatterplot(x='judge_empathy_validation', y='final_completion_percent', hue='persona', data=df, s=100)
    plt.title('Learning Efficacy vs Empathy', fontsize=14)
    plt.xlabel('LLM Judge: Empathy & Validation Score')
    plt.ylabel('Final Completion Percent (%)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_scatter_efficacy_vs_empathy.png"))
    plt.close()

def plot_curriculum_bottlenecks(df_bottlenecks: pd.DataFrame, output_dir: str):
    if df_bottlenecks.empty: return
    plt.figure(figsize=(12, 6))
    grouped = df_bottlenecks.groupby(['section_id', 'persona'])['turns_spent'].mean().unstack().fillna(0)
    grouped.plot(kind='bar', stacked=True, figsize=(12, 6), colormap='viridis')
    plt.title('Curriculum Bottlenecks: Average Turns Spent per Section', fontsize=14)
    plt.ylabel('Average Turns Spent')
    plt.xlabel('Curriculum Section ID')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_stacked_bar_bottlenecks.png"))
    plt.close()

def plot_hint_progression(df: pd.DataFrame, output_dir: str):
    if 'turns_with_hints' not in df.columns or 'turns_at_max_hints' not in df.columns: return
    total_hints = df['turns_with_hints'].sum()
    max_hints = df['turns_at_max_hints'].sum()
    
    plt.figure(figsize=(8, 6))
    sns.barplot(x=['Turns with 1+ Hints', 'Turns at Max Hints (Exhaustion)'], y=[total_hints, max_hints], palette='Blues_r')
    plt.title('Hint Progression Drop-off (Anti-Spoiler)', fontsize=14)
    plt.ylabel('Total Turns across all sessions')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_bar_hint_progression.png"))
    plt.close()

def plot_intervention_success(df: pd.DataFrame, output_dir: str):
    if 'intervention_success_rate' not in df.columns: return
    plt.figure(figsize=(10, 6))
    sns.barplot(x='persona', y='intervention_success_rate', data=df, errorbar=None)
    plt.title('Average Intervention Success Rate per Persona', fontsize=14)
    plt.ylabel('Success Rate (0 to 1.0)')
    plt.xlabel('Persona')
    plt.ylim(0, 1.0)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_bar_intervention_success.png"))
    plt.close()

def plot_emotion_distribution(df: pd.DataFrame, output_dir: str):
    emotion_cols = [c for c in df.columns if c.startswith('emotion_')]
    if not emotion_cols: return
    grouped = df.groupby('persona')[emotion_cols].mean()
    grouped.columns = [c.replace('emotion_', '').title() for c in grouped.columns]
    
    # Normalize to 100% just in case
    row_sums = grouped.sum(axis=1)
    # Avoid division by zero
    grouped = grouped.div(row_sums.replace(0, 1), axis=0) * 100
    
    grouped.plot(kind='bar', stacked=True, figsize=(10, 6), colormap='Set3')
    plt.title('Overall Emotion Distribution by Persona', fontsize=14)
    plt.ylabel('Percentage (%)')
    plt.xlabel('Persona')
    plt.legend(title='Emotion', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_stacked_bar_emotions.png"))
    plt.close()

def plot_boredom_vs_gaze(df: pd.DataFrame, output_dir: str):
    if 'time_to_boredom_turn' not in df.columns or 'gaze_away_percentage' not in df.columns: return
    
    # Drop rows where time_to_boredom_turn is null for the scatter plot
    df_plot = df.dropna(subset=['time_to_boredom_turn'])
    if df_plot.empty: return

    plt.figure(figsize=(10, 6))
    sns.scatterplot(x='time_to_boredom_turn', y='gaze_away_percentage', hue='persona', data=df_plot, s=100)
    plt.title('Time to Boredom vs Gaze Away Percentage', fontsize=14)
    plt.xlabel('Turn Number When Boredom Detected')
    plt.ylabel('Gaze Away Percentage (%)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_scatter_boredom_vs_gaze.png"))
    plt.close()

def plot_talk_ratio_vs_socratic(df: pd.DataFrame, output_dir: str):
    if 'student_tutor_talk_ratio' not in df.columns or 'judge_socratic_adherence' not in df.columns: return
    plt.figure(figsize=(10, 6))
    sns.scatterplot(x='student_tutor_talk_ratio', y='judge_socratic_adherence', hue='persona', data=df, s=100)
    plt.title('Student/Tutor Talk Ratio vs Socratic Adherence', fontsize=14)
    plt.xlabel('Student to Tutor Talk Ratio')
    plt.ylabel('LLM Judge: Socratic Adherence Score')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_scatter_talk_ratio_vs_socratic.png"))
    plt.close()

def plot_vocab_adoption_delay(df: pd.DataFrame, output_dir: str):
    if 'avg_adoption_delay_turns' not in df.columns: return
    plt.figure(figsize=(10, 6))
    # Passing palette without hue is deprecated, assigning x to hue fixes the warning
    sns.barplot(x='persona', y='avg_adoption_delay_turns', hue='persona', data=df, errorbar=None, palette='pastel', legend=False)
    plt.title('Average Vocabulary Adoption Delay', fontsize=14)
    plt.ylabel('Delay (Turns)')
    plt.xlabel('Persona')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_bar_vocab_adoption_delay.png"))
    plt.close()

def plot_token_efficiency(df: pd.DataFrame, output_dir: str):
    if 'avg_tokens_per_turn' not in df.columns or 'final_completion_percent' not in df.columns: return
    plt.figure(figsize=(10, 6))
    sns.scatterplot(x='avg_tokens_per_turn', y='final_completion_percent', hue='persona', data=df, s=100)
    plt.title('Token Efficiency: Average Tokens per Turn vs Final Completion', fontsize=14)
    plt.xlabel('Average Tokens per Turn')
    plt.ylabel('Final Completion Percent (%)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "aggregated_scatter_token_efficiency.png"))
    plt.close()

def plot_latency_by_agent(df_turns: pd.DataFrame, output_dir: str):
    if df_turns.empty or 'pipeline_latency_ms' not in df_turns.columns: return
    plt.figure(figsize=(12, 6))
    sns.boxplot(x='persona', y='pipeline_latency_ms', hue='primary_agent', data=df_turns)
    plt.title('Latency by Agent Type per Persona', fontsize=14)
    plt.ylabel('Pipeline Latency (ms)')
    plt.xticks(rotation=45)
    plt.legend(title='Primary Agent', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "turn_latency_by_agent_per_persona.png"))
    plt.close()

def plot_turn_latency_trajectory(df_turns: pd.DataFrame, output_dir: str):
    if df_turns.empty or 'pipeline_latency_ms' not in df_turns.columns: return
    plt.figure(figsize=(12, 6))
    sns.lineplot(x='turn_count', y='pipeline_latency_ms', hue='persona', data=df_turns, marker='o')
    plt.title('Turn-by-Turn Latency Trajectory', fontsize=14)
    plt.xlabel('Turn Count')
    plt.ylabel('Pipeline Latency (ms)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "turn_latency_trajectory.png"))
    plt.close()

def plot_agent_transition_heatmap(df_turns: pd.DataFrame, output_dir: str):
    if df_turns.empty or 'primary_agent' not in df_turns.columns: return
    
    # Group by session to calculate transitions
    transitions = []
    for _, session_df in df_turns.groupby('session_id'):
        session_df = session_df.sort_values('turn_count')
        persona = session_df['persona'].iloc[0]
        agents = session_df['primary_agent'].tolist()
        for i in range(len(agents)-1):
            transitions.append({
                'persona': persona,
                'from_agent': agents[i],
                'to_agent': agents[i+1]
            })
            
    if not transitions: return
    trans_df = pd.DataFrame(transitions)
    
    # Save a heatmap for each persona
    for persona, p_df in trans_df.groupby('persona'):
        crosstab = pd.crosstab(p_df['from_agent'], p_df['to_agent'], normalize='index') * 100
        plt.figure(figsize=(8, 6))
        sns.heatmap(crosstab, annot=True, fmt=".1f", cmap="YlGnBu", vmin=0, vmax=100)
        plt.title(f'Agent Transition Heatmap (%) - {persona}', fontsize=14)
        plt.ylabel('From Agent')
        plt.xlabel('To Agent')
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, f"agent_transition_heatmap_{persona}.png"))
        plt.close()

# ═══════════════════════════════════════════════════════════════
# SESSION-SPECIFIC VISUALIZATIONS
# ═══════════════════════════════════════════════════════════════

def plot_session_specific_charts(session: dict, base_output_dir: str):
    """Generates specific charts for a single session and saves them in an organized folder."""
    session_id = session.get("session_id", "unknown_session")
    persona = session.get("persona", "unknown_persona")
    
    # Create a specific folder for this session
    session_dir = os.path.join(base_output_dir, "sessions", f"{persona}_{session_id}")
    os.makedirs(session_dir, exist_ok=True)
    
    # 1. Session Radar Chart
    judge_scores = session.get("llm_judge_scores", {})
    categories = []
    values = []
    for metric in [
        "socratic_adherence", "empathy_validation", "age_appropriate_tone",
        "guardrail_resilience", "curriculum_grounding", "faithfulness",
        "answer_relevance", "concept_leakage", "hint_progression_compliance",
        "tone_consistency", "off_topic_deflection", "prompt_injection_resilience"
    ]:
        if metric in judge_scores and isinstance(judge_scores[metric], dict):
            categories.append(metric.replace('_', ' ').title())
            values.append(judge_scores[metric].get("score", 0))
            
    if categories and values:
        N = len(categories)
        angles = [n / float(N) * 2 * pi for n in range(N)]
        angles += angles[:1]
        values += values[:1]
        
        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
        ax.plot(angles, values, linewidth=2, linestyle='solid', color='purple')
        ax.fill(angles, values, alpha=0.25, color='purple')
        plt.xticks(angles[:-1], categories, size=9)
        ax.set_ylim(0, 10)
        plt.title(f'LLM Judge Scores\\nPersona: {persona}\\nSession: {session_id[:8]}...', size=13, y=1.1)
        plt.tight_layout()
        plt.savefig(os.path.join(session_dir, "session_radar_chart.png"))
        plt.close()
        
    # 2. Session Completion Trajectory
    trajectory = session.get("completion_trajectory", [])
    if trajectory:
        turns = [t.get("turn", 0) for t in trajectory]
        percents = [t.get("percent", 0) for t in trajectory]
        
        plt.figure(figsize=(8, 5))
        plt.plot(turns, percents, marker='o', linestyle='-', color='b')
        plt.fill_between(turns, percents, color='b', alpha=0.1)
        plt.title(f'Learning Completion Trajectory\\nSession: {session_id[:8]}...', fontsize=12)
        plt.xlabel('Turn Count')
        plt.ylabel('Completion Percent (%)')
        plt.ylim(-5, 105)
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(os.path.join(session_dir, "session_completion_trajectory.png"))
        plt.close()

    # 3. Session Agent Activation Pie Chart
    agents = session.get("agent_activation_distribution", {})
    if agents:
        labels = [k.title() for k in agents.keys()]
        sizes = [v.get("percent", 0) for v in agents.values()]
        
        # Only plot if there's actual data
        if sum(sizes) > 0:
            plt.figure(figsize=(7, 7))
            plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=sns.color_palette("pastel"))
            plt.title(f'Agent Activation Distribution\\nSession: {session_id[:8]}...')
            plt.tight_layout()
            plt.savefig(os.path.join(session_dir, "session_agent_activation.png"))
            plt.close()

    # 4. Session Curriculum Bottlenecks
    bottlenecks = session.get("section_bottlenecks", [])
    if bottlenecks:
        sections = [b.get("section_id", "Unknown") for b in bottlenecks]
        turns_spent = [b.get("turns_spent", 0) for b in bottlenecks]
        
        plt.figure(figsize=(8, 5))
        sns.barplot(x=sections, y=turns_spent, palette='magma')
        plt.title(f'Turns Spent per Curriculum Section\\nSession: {session_id[:8]}...', fontsize=12)
        plt.xlabel('Curriculum Section ID')
        plt.ylabel('Turns Spent')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(session_dir, "session_section_bottlenecks.png"))
        plt.close()

    # 5. Session Hint Progression
    hints = session.get("hint_exhaustion_rate", {})
    t_hints = hints.get("turns_with_hints", 0)
    t_max = hints.get("turns_at_max_hints", 0)
    
    if t_hints > 0 or t_max > 0:
        plt.figure(figsize=(6, 5))
        sns.barplot(x=['1+ Hints', 'Max Hints'], y=[t_hints, t_max], palette='Blues_r')
        plt.title(f'Hint Progression / Exhaustion\\nSession: {session_id[:8]}...', fontsize=12)
        plt.ylabel('Turn Count')
        plt.tight_layout()
        plt.savefig(os.path.join(session_dir, "session_hint_progression.png"))
        plt.close()

if __name__ == "__main__":
    import datetime
    # Assuming script is run from e:\PALM_fyp\scripts
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    viz_dir = os.path.join(workspace_root, "evaluations", "analysis", "visualizations", f"run_{timestamp}")
    agg_dir = os.path.join(viz_dir, "aggregated")
    
    os.makedirs(agg_dir, exist_ok=True)
    
    print(f"Loading data from {workspace_root}...")
    df_sessions, df_bottlenecks, df_turns, raw_sessions = load_evaluation_data(workspace_root)
    
    if df_sessions.empty:
        print("No JSON evaluation data found.")
    else:
        print(f"Loaded {len(df_sessions)} session reports. Generating aggregated visualizations...")
        
        # 1. Generate Aggregated Visualizations
        plot_aggregated_radar_chart(df_sessions, agg_dir)
        plot_heatmap_metrics(df_sessions, agg_dir)
        plot_latency_boxplot(df_sessions, agg_dir)
        plot_token_cost_bar(df_sessions, agg_dir)
        plot_learning_efficacy_scatter(df_sessions, agg_dir)
        plot_curriculum_bottlenecks(df_bottlenecks, agg_dir)
        plot_hint_progression(df_sessions, agg_dir)
        plot_intervention_success(df_sessions, agg_dir)
        plot_emotion_distribution(df_sessions, agg_dir)
        plot_boredom_vs_gaze(df_sessions, agg_dir)
        plot_talk_ratio_vs_socratic(df_sessions, agg_dir)
        plot_vocab_adoption_delay(df_sessions, agg_dir)
        plot_token_efficiency(df_sessions, agg_dir)
        
        # Turn-level Visualizations
        if not df_turns.empty:
            plot_latency_by_agent(df_turns, agg_dir)
            plot_turn_latency_trajectory(df_turns, agg_dir)
            plot_agent_transition_heatmap(df_turns, agg_dir)
        
        # 2. Generate Session-Specific Visualizations
        print(f"Generating session-specific visualizations for {len(raw_sessions)} sessions...")
        for session_data in raw_sessions:
            plot_session_specific_charts(session_data, viz_dir)
            
        print(f"All visualizations saved successfully to: {viz_dir}")
