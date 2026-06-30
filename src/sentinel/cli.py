#!/usr/bin/env python3
"""
Sentinel CLI - Command-line interface for learning analytics.

Commands:
    sentinel stats          Show learning statistics
    sentinel patterns       List learned patterns
    sentinel failures       Show recent failures
    sentinel learn          Manually add a pattern
    sentinel export         Export patterns to file

Examples:
    sentinel stats --detailed
    sentinel patterns --min-confidence 0.7
    sentinel failures --limit 50
    sentinel learn "years of experience" "3-5 years"
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sentinel.self_healing import SelfHealingMatcher
from src.patterns.pattern_learner import PatternLearner


class SentinelCLI:
    """CLI for Sentinel learning system."""
    
    def __init__(self):
        self.storage_dir = Path.home() / "Desktop" / "sentinel_errors"
        self.self_healing = SelfHealingMatcher(str(self.storage_dir))
        self.pattern_learner = PatternLearner()
    
    def stats(self, detailed: bool = False, json_output: bool = False) -> str:
        """Show learning statistics."""
        stats = self.self_healing.get_stats()
        patterns = list(self.self_healing.learning_store.patterns.values())
        
        # Calculate additional metrics
        high_conf = [p for p in patterns if p.confidence >= 0.8]
        medium_conf = [p for p in patterns if 0.5 <= p.confidence < 0.8]
        low_conf = [p for p in patterns if p.confidence < 0.5]
        
        # Recovery stats
        # Note: We'd need to persist pipeline stats, for now use placeholder
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'patterns': {
                'total': stats['total_patterns'],
                'high_confidence': len(high_conf),
                'medium_confidence': len(medium_conf),
                'low_confidence': len(low_conf),
                'confident': stats['confident_patterns'],
                'avg_confidence': stats['avg_confidence'],
                'total_uses': stats['total_uses'],
                'total_successes': stats['total_successes']
            },
            'performance': {
                'overall_success_rate': stats['total_successes'] / max(1, stats['total_uses']),
            }
        }
        
        if json_output:
            return json.dumps(data, indent=2)
        
        # Format as table
        output = []
        output.append("╔══════════════════════════════════════════════════════════════╗")
        output.append("║                    LEARNING STATISTICS                        ║")
        output.append("╠══════════════════════════════════════════════════════════════╣")
        output.append(f"║ Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):45} ║")
        output.append("╠══════════════════════════════════════════════════════════════╣")
        output.append("║ PATTERNS                                                      ║")
        output.append(f"║   Total:              {stats['total_patterns']:4d}                                    ║")
        output.append(f"║   High confidence:    {len(high_conf):4d} (>= 0.8)                           ║")
        output.append(f"║   Medium confidence:  {len(medium_conf):4d} (0.5-0.8)                        ║")
        output.append(f"║   Low confidence:     {len(low_conf):4d} (< 0.5)                             ║")
        output.append("║                                                               ║")
        output.append("║ PERFORMANCE                                                   ║")
        success_rate = stats['total_successes'] / max(1, stats['total_uses'])
        output.append(f"║   Total uses:         {stats['total_uses']:4d}                                    ║")
        output.append(f"║   Successful:         {stats['total_successes']:4d} ({success_rate:5.1%})                        ║")
        output.append(f"║   Average confidence: {stats['avg_confidence']:5.2f}                                ║")
        output.append("╚══════════════════════════════════════════════════════════════╝")
        
        if detailed:
            output.append("")
            output.append("TOP 10 PATTERNS (by confidence):")
            output.append("-" * 70)
            top_patterns = sorted(
                patterns,
                key=lambda p: p.confidence,
                reverse=True
            )[:10]
            
            for i, p in enumerate(top_patterns, 1):
                q_preview = p.question_patterns[0][:40] if p.question_patterns else "N/A"
                output.append(f"{i:2d}. {q_preview:40s} | Conf: {p.confidence:.2f} | Uses: {p.times_used}")
        
        return "\n".join(output)
    
    def patterns(
        self,
        min_confidence: float = 0.5,
        category: str = None,
        json_output: bool = False
    ) -> str:
        """List learned patterns."""
        patterns = list(self.self_healing.learning_store.patterns.values())
        
        # Filter by confidence
        patterns = [p for p in patterns if p.confidence >= min_confidence]
        
        # Filter by category if specified
        if category:
            patterns = [
                p for p in patterns
                if category.lower() in p.learned_from.lower()
            ]
        
        # Sort by confidence
        patterns = sorted(patterns, key=lambda p: p.confidence, reverse=True)
        
        if json_output:
            data = {
                'patterns': [
                    {
                        'id': p.pattern_id,
                        'questions': p.question_patterns,
                        'answer': p.answer,
                        'confidence': p.confidence,
                        'uses': p.times_used,
                        'successes': p.times_succeeded,
                        'success_rate': p.success_rate,
                        'learned_from': p.learned_from,
                        'created': p.created_at
                    }
                    for p in patterns
                ]
            }
            return json.dumps(data, indent=2)
        
        # Format as table
        output = []
        output.append(f"PATTERNS (confidence >= {min_confidence}, total: {len(patterns)})")
        output.append("-" * 100)
        output.append(f"{'Question':<50} {'Answer':<25} {'Conf':>6} {'Uses':>6} {'Rate':>6}")
        output.append("-" * 100)
        
        for p in patterns[:50]:  # Limit to 50 for display
            q = p.question_patterns[0][:48] if p.question_patterns else "N/A"
            a = p.answer[:23] if len(p.answer) > 23 else p.answer
            rate = f"{p.success_rate:.0%}" if p.times_used > 0 else "N/A"
            output.append(
                f"{q:<50} {a:<25} {p.confidence:>6.2f} {p.times_used:>6} {rate:>6}"
            )
        
        if len(patterns) > 50:
            output.append(f"\n... and {len(patterns) - 50} more patterns")
        
        return "\n".join(output)
    
    def failures(self, limit: int = 20, json_output: bool = False) -> str:
        """Show recent failures."""
        # Read from failure log
        failure_log = self.storage_dir / "failure_log.jsonl"
        
        if not failure_log.exists():
            return "No failures logged yet."
        
        failures = []
        try:
            with open(failure_log, 'r') as f:
                for line in f:
                    try:
                        failures.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            return f"Error reading failure log: {e}"
        
        # Get most recent
        failures = failures[-limit:]
        
        if json_output:
            return json.dumps({'failures': failures}, indent=2)
        
        # Format as table
        output = []
        output.append(f"RECENT FAILURES (last {len(failures)})")
        output.append("-" * 90)
        
        for f in reversed(failures):  # Most recent first
            ts = f.get('timestamp', 'Unknown')[:19]
            q = f.get('question', 'N/A')[:40]
            attempted = f.get('attempted_answer', 'N/A')[:20]
            error = f.get('error_type', 'Unknown')
            platform = f.get('platform', 'Unknown')
            
            output.append(f"[{ts}] [{platform}]")
            output.append(f"  Q: {q}")
            output.append(f"  Attempted: {attempted}")
            output.append(f"  Error: {error}")
            output.append("")
        
        return "\n".join(output)
    
    def learn(self, question: str, answer: str, category: str = "manual") -> str:
        """Manually add a pattern."""
        pattern_id = self.self_healing.learning_store.add_pattern(
            question=question,
            answer=answer,
            option_mapping={},
            source=f'manual_cli_{category}'
        )
        
        # Boost confidence for manually added patterns
        pattern = self.self_healing.learning_store.patterns.get(pattern_id)
        if pattern:
            pattern.confidence = 0.8  # Higher confidence for manual entry
            self.self_healing.learning_store._save()
        
        # Also learn in pattern learner for semantic matching
        self.pattern_learner.learn_from_success(question, answer)
        
        return f"✅ Pattern learned: '{question[:50]}...' -> '{answer}'\n   ID: {pattern_id}\n   Confidence: 0.80"
    
    def export(self, output_file: str, min_confidence: float = 0.5) -> str:
        """Export patterns to file."""
        patterns = list(self.self_healing.learning_store.patterns.values())
        patterns = [p for p in patterns if p.confidence >= min_confidence]
        
        data = {
            'export_metadata': {
                'timestamp': datetime.now().isoformat(),
                'total_patterns': len(patterns),
                'min_confidence': min_confidence
            },
            'patterns': {
                p.pattern_id: {
                    'question_patterns': p.question_patterns,
                    'answer': p.answer,
                    'confidence': p.confidence,
                    'learned_from': p.learned_from
                }
                for p in patterns
            }
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        return f"✅ Exported {len(patterns)} patterns to {output_file}"


def main():
    """Main CLI entry point."""
    cli = SentinelCLI()
    
    parser = argparse.ArgumentParser(
        description='Sentinel Learning System CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sentinel stats                    Show basic statistics
  sentinel stats -d                 Show detailed statistics
  sentinel patterns                 List all patterns
  sentinel patterns -c 0.7          List patterns with confidence >= 0.7
  sentinel failures -l 50           Show last 50 failures
  sentinel learn "exp" "3-5 years"  Manually add a pattern
  sentinel export patterns.json     Export patterns to JSON
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # stats command
    stats_parser = subparsers.add_parser('stats', help='Show learning statistics')
    stats_parser.add_argument('-d', '--detailed', action='store_true',
                             help='Show detailed statistics')
    stats_parser.add_argument('--json', action='store_true',
                             help='Output as JSON')
    
    # patterns command
    patterns_parser = subparsers.add_parser('patterns', help='List learned patterns')
    patterns_parser.add_argument('-c', '--min-confidence', type=float, default=0.5,
                                help='Minimum confidence threshold (default: 0.5)')
    patterns_parser.add_argument('--category', type=str,
                                help='Filter by category')
    patterns_parser.add_argument('--json', action='store_true',
                                help='Output as JSON')
    
    # failures command
    failures_parser = subparsers.add_parser('failures', help='Show recent failures')
    failures_parser.add_argument('-l', '--limit', type=int, default=20,
                                help='Number of failures to show (default: 20)')
    failures_parser.add_argument('--json', action='store_true',
                                help='Output as JSON')
    
    # learn command
    learn_parser = subparsers.add_parser('learn', help='Manually add a pattern')
    learn_parser.add_argument('question', help='Question pattern')
    learn_parser.add_argument('answer', help='Answer value')
    learn_parser.add_argument('--category', default='manual',
                             help='Category for the pattern')
    
    # export command
    export_parser = subparsers.add_parser('export', help='Export patterns to file')
    export_parser.add_argument('output', help='Output file path')
    export_parser.add_argument('-c', '--min-confidence', type=float, default=0.5,
                              help='Minimum confidence threshold (default: 0.5)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Execute command
    if args.command == 'stats':
        print(cli.stats(detailed=args.detailed, json_output=args.json))
    
    elif args.command == 'patterns':
        print(cli.patterns(
            min_confidence=args.min_confidence,
            category=args.category,
            json_output=args.json
        ))
    
    elif args.command == 'failures':
        print(cli.failures(limit=args.limit, json_output=args.json))
    
    elif args.command == 'learn':
        print(cli.learn(args.question, args.answer, args.category))
    
    elif args.command == 'export':
        print(cli.export(args.output, args.min_confidence))


if __name__ == '__main__':
    main()
