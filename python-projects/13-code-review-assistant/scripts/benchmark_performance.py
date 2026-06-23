#!/usr/bin/env python3
"""
Performance Benchmarking Script
Measures database query performance, API response times, and system throughput
"""

import sys
import os
import time
import json
import statistics
from typing import List, Dict, Any
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.database import DatabaseManager, CodeFile, Issue, PullRequest, Repository, User
from src.core.database import IssueSeverity, IssueCategory, PRStatus
from sqlalchemy import func


class PerformanceBenchmark:
    """Performance benchmarking suite"""

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.results = []

    def benchmark(self, name: str, func, iterations: int = 10):
        """
        Benchmark a function

        Args:
            name: Benchmark name
            func: Function to benchmark
            iterations: Number of iterations

        Returns:
            Benchmark results
        """
        print(f"\n📊 Benchmarking: {name}")
        print(f"   Iterations: {iterations}")

        times = []
        for i in range(iterations):
            start = time.time()
            try:
                func()
                elapsed = time.time() - start
                times.append(elapsed)
                print(f"   Run {i+1}/{iterations}: {elapsed*1000:.2f}ms")
            except Exception as e:
                print(f"   Run {i+1}/{iterations}: ERROR - {e}")
                continue

        if times:
            avg_time = statistics.mean(times)
            median_time = statistics.median(times)
            min_time = min(times)
            max_time = max(times)
            stddev = statistics.stdev(times) if len(times) > 1 else 0

            result = {
                'name': name,
                'iterations': len(times),
                'avg_ms': avg_time * 1000,
                'median_ms': median_time * 1000,
                'min_ms': min_time * 1000,
                'max_ms': max_time * 1000,
                'stddev_ms': stddev * 1000,
                'timestamp': datetime.utcnow().isoformat()
            }

            self.results.append(result)

            print(f"\n   ✅ Results:")
            print(f"      Average: {avg_time*1000:.2f}ms")
            print(f"      Median:  {median_time*1000:.2f}ms")
            print(f"      Min:     {min_time*1000:.2f}ms")
            print(f"      Max:     {max_time*1000:.2f}ms")
            print(f"      StdDev:  {stddev*1000:.2f}ms")

            return result
        else:
            print("   ❌ All iterations failed")
            return None

    def benchmark_db_queries(self):
        """Benchmark common database queries"""
        print("\n" + "="*60)
        print("DATABASE QUERY BENCHMARKS")
        print("="*60)

        with self.db_manager.get_session() as db:
            # 1. Count all issues
            self.benchmark(
                "Count all issues",
                lambda: db.query(Issue).count(),
                iterations=20
            )

            # 2. Count issues by severity
            self.benchmark(
                "Count issues by severity",
                lambda: db.query(Issue.severity, func.count(Issue.id)).group_by(Issue.severity).all(),
                iterations=20
            )

            # 3. Get issues for a PR (with file join)
            pr = db.query(PullRequest).first()
            if pr:
                self.benchmark(
                    "Get issues for PR (with join)",
                    lambda: db.query(Issue).join(CodeFile).filter(
                        CodeFile.pull_request_id == pr.id
                    ).all(),
                    iterations=15
                )

            # 4. Get recent issues (last 30 days)
            threshold = datetime.utcnow() - timedelta(days=30)
            self.benchmark(
                "Get recent issues (30 days)",
                lambda: db.query(Issue).filter(Issue.created_at >= threshold).all(),
                iterations=15
            )

            # 5. Complex query: issues by category and severity
            self.benchmark(
                "Group by category and severity",
                lambda: db.query(
                    Issue.category,
                    Issue.severity,
                    func.count(Issue.id)
                ).group_by(Issue.category, Issue.severity).all(),
                iterations=15
            )

            # 6. Get code files by language
            self.benchmark(
                "Get code files by language",
                lambda: db.query(CodeFile).filter(CodeFile.language == 'python').all(),
                iterations=15
            )

            # 7. Get PRs with repository join
            self.benchmark(
                "Get PRs with repository (join)",
                lambda: db.query(PullRequest).join(Repository).all(),
                iterations=15
            )

            # 8. Count PRs by status
            self.benchmark(
                "Count PRs by status",
                lambda: db.query(PullRequest.status, func.count(PullRequest.id)).group_by(
                    PullRequest.status
                ).all(),
                iterations=20
            )

    def benchmark_db_writes(self):
        """Benchmark database write operations"""
        print("\n" + "="*60)
        print("DATABASE WRITE BENCHMARKS")
        print("="*60)

        with self.db_manager.get_session() as db:
            # Get or create test user and repository
            user = db.query(User).first()
            if not user:
                print("⚠️  No users found, skipping write benchmarks")
                return

            repo = db.query(Repository).first()
            if not repo:
                print("⚠️  No repositories found, skipping write benchmarks")
                return

            # 1. Create PR
            def create_pr():
                pr = PullRequest(
                    repository_id=repo.id,
                    pr_number=99999,
                    title="Benchmark PR",
                    source_branch="benchmark",
                    target_branch="main",
                    status=PRStatus.OPEN
                )
                db.add(pr)
                db.flush()
                db.delete(pr)  # Clean up
                db.flush()

            self.benchmark("Create and delete PR", create_pr, iterations=10)

            # 2. Create issue
            pr = db.query(PullRequest).first()
            if pr and pr.code_files:
                code_file = pr.code_files[0]

                def create_issue():
                    issue = Issue(
                        code_file_id=code_file.id,
                        category=IssueCategory.SMELL,
                        severity=IssueSeverity.INFO,
                        rule_id='BENCH001',
                        title='Benchmark Issue',
                        description='Performance test',
                        line_number=1
                    )
                    db.add(issue)
                    db.flush()
                    db.delete(issue)  # Clean up
                    db.flush()

                self.benchmark("Create and delete issue", create_issue, iterations=10)

    def benchmark_aggregations(self):
        """Benchmark complex aggregations"""
        print("\n" + "="*60)
        print("AGGREGATION BENCHMARKS")
        print("="*60)

        with self.db_manager.get_session() as db:
            # 1. Calculate total LOC
            self.benchmark(
                "Sum total lines of code",
                lambda: db.query(func.sum(CodeFile.lines_of_code)).scalar(),
                iterations=20
            )

            # 2. Average issues per file
            self.benchmark(
                "Average issues per file",
                lambda: db.query(func.avg(func.count(Issue.id))).select_from(CodeFile).join(
                    Issue
                ).group_by(CodeFile.id).scalar(),
                iterations=15
            )

            # 3. Max/min issue counts
            self.benchmark(
                "Max/min issue counts per file",
                lambda: db.query(
                    func.max(func.count(Issue.id)),
                    func.min(func.count(Issue.id))
                ).select_from(CodeFile).join(Issue).group_by(CodeFile.id).first(),
                iterations=15
            )

    def save_results(self, filename: str = "benchmark_results.json"):
        """Save benchmark results to file"""
        output_path = os.path.join(os.path.dirname(__file__), '..', 'data', filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump({
                'timestamp': datetime.utcnow().isoformat(),
                'results': self.results
            }, f, indent=2)

        print(f"\n💾 Results saved to: {output_path}")

    def print_summary(self):
        """Print benchmark summary"""
        print("\n" + "="*60)
        print("BENCHMARK SUMMARY")
        print("="*60)

        if not self.results:
            print("No results to summarize")
            return

        print(f"\nTotal benchmarks: {len(self.results)}")
        print(f"\nTop 5 Fastest Operations:")
        sorted_by_avg = sorted(self.results, key=lambda x: x['avg_ms'])
        for i, result in enumerate(sorted_by_avg[:5], 1):
            print(f"  {i}. {result['name']}: {result['avg_ms']:.2f}ms")

        print(f"\nTop 5 Slowest Operations:")
        for i, result in enumerate(sorted(self.results, key=lambda x: x['avg_ms'], reverse=True)[:5], 1):
            print(f"  {i}. {result['name']}: {result['avg_ms']:.2f}ms")

        # Performance grades
        print(f"\nPerformance Grades:")
        for result in self.results:
            avg = result['avg_ms']
            if avg < 10:
                grade = "🟢 Excellent"
            elif avg < 50:
                grade = "🟡 Good"
            elif avg < 100:
                grade = "🟠 Fair"
            else:
                grade = "🔴 Slow"

            print(f"  {result['name']}: {avg:.2f}ms - {grade}")


def main():
    """Main benchmark runner"""
    print("\n" + "="*60)
    print("AI CODE REVIEW ASSISTANT - PERFORMANCE BENCHMARKS")
    print("="*60)
    print(f"Started at: {datetime.utcnow().isoformat()}")

    benchmark = PerformanceBenchmark()

    try:
        # Run benchmarks
        benchmark.benchmark_db_queries()
        benchmark.benchmark_db_writes()
        benchmark.benchmark_aggregations()

        # Print summary
        benchmark.print_summary()

        # Save results
        benchmark.save_results()

        print("\n✅ Benchmarking complete!")

    except Exception as e:
        print(f"\n❌ Error during benchmarking: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
