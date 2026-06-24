#!/usr/bin/env python3
"""
Load Testing Script
Tests system performance under heavy load
"""

import time
import asyncio
import aiohttp
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Callable
import argparse
import json
from datetime import datetime


class LoadTester:
    """Load testing utility"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results = []

    def run_sequential_test(self, endpoint: str, num_requests: int = 100) -> Dict:
        """
        Run sequential load test

        Args:
            endpoint: API endpoint to test
            num_requests: Number of requests to make

        Returns:
            Dictionary with test results
        """
        print(f"\n{'='*60}")
        print(f"Sequential Load Test: {endpoint}")
        print(f"Requests: {num_requests}")
        print(f"{'='*60}")

        import requests

        times = []
        errors = 0
        status_codes = {}

        start_time = time.time()

        for i in range(num_requests):
            request_start = time.time()

            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=30)
                request_time = time.time() - request_start
                times.append(request_time)

                status = response.status_code
                status_codes[status] = status_codes.get(status, 0) + 1

                if status >= 400:
                    errors += 1

            except Exception as e:
                errors += 1
                request_time = time.time() - request_start
                times.append(request_time)
                print(f"Error on request {i+1}: {e}")

            # Progress indicator
            if (i + 1) % 10 == 0:
                print(f"Progress: {i+1}/{num_requests} ({(i+1)/num_requests*100:.1f}%)")

        total_time = time.time() - start_time

        return self._calculate_stats(times, errors, total_time, num_requests, status_codes)

    def run_concurrent_test(self, endpoint: str, num_requests: int = 100, max_workers: int = 10) -> Dict:
        """
        Run concurrent load test

        Args:
            endpoint: API endpoint to test
            num_requests: Total number of requests
            max_workers: Maximum concurrent workers

        Returns:
            Dictionary with test results
        """
        print(f"\n{'='*60}")
        print(f"Concurrent Load Test: {endpoint}")
        print(f"Requests: {num_requests}, Workers: {max_workers}")
        print(f"{'='*60}")

        import requests

        def make_request(request_num):
            request_start = time.time()
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=30)
                request_time = time.time() - request_start
                return {
                    'time': request_time,
                    'status': response.status_code,
                    'error': None
                }
            except Exception as e:
                request_time = time.time() - request_start
                return {
                    'time': request_time,
                    'status': None,
                    'error': str(e)
                }

        times = []
        errors = 0
        status_codes = {}

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(make_request, i) for i in range(num_requests)]

            completed = 0
            for future in as_completed(futures):
                result = future.result()
                times.append(result['time'])

                if result['error']:
                    errors += 1
                else:
                    status = result['status']
                    status_codes[status] = status_codes.get(status, 0) + 1
                    if status >= 400:
                        errors += 1

                completed += 1
                if completed % 10 == 0:
                    print(f"Completed: {completed}/{num_requests} ({completed/num_requests*100:.1f}%)")

        total_time = time.time() - start_time

        return self._calculate_stats(times, errors, total_time, num_requests, status_codes)

    async def run_async_test(self, endpoint: str, num_requests: int = 100, concurrency: int = 10) -> Dict:
        """
        Run async load test with aiohttp

        Args:
            endpoint: API endpoint to test
            num_requests: Total number of requests
            concurrency: Number of concurrent requests

        Returns:
            Dictionary with test results
        """
        print(f"\n{'='*60}")
        print(f"Async Load Test: {endpoint}")
        print(f"Requests: {num_requests}, Concurrency: {concurrency}")
        print(f"{'='*60}")

        times = []
        errors = 0
        status_codes = {}

        async def make_request(session, request_num):
            request_start = time.time()
            try:
                async with session.get(f"{self.base_url}{endpoint}") as response:
                    await response.text()  # Ensure full response is read
                    request_time = time.time() - request_start
                    return {
                        'time': request_time,
                        'status': response.status,
                        'error': None
                    }
            except Exception as e:
                request_time = time.time() - request_start
                return {
                    'time': request_time,
                    'status': None,
                    'error': str(e)
                }

        start_time = time.time()

        async with aiohttp.ClientSession() as session:
            # Create batches to control concurrency
            for i in range(0, num_requests, concurrency):
                batch_size = min(concurrency, num_requests - i)
                tasks = [make_request(session, i + j) for j in range(batch_size)]
                results = await asyncio.gather(*tasks)

                for result in results:
                    times.append(result['time'])
                    if result['error']:
                        errors += 1
                    else:
                        status = result['status']
                        status_codes[status] = status_codes.get(status, 0) + 1
                        if status >= 400:
                            errors += 1

                completed = i + batch_size
                print(f"Completed: {completed}/{num_requests} ({completed/num_requests*100:.1f}%)")

        total_time = time.time() - start_time

        return self._calculate_stats(times, errors, total_time, num_requests, status_codes)

    def test_large_file_upload(self, file_size_mb: int = 5) -> Dict:
        """
        Test large file upload

        Args:
            file_size_mb: Size of file to upload in MB

        Returns:
            Test results
        """
        print(f"\n{'='*60}")
        print(f"Large File Upload Test: {file_size_mb}MB")
        print(f"{'='*60}")

        import requests
        import tempfile

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            # Generate file content
            content = "# Test file\n" + ("x" * (file_size_mb * 1024 * 1024))
            f.write(content)
            temp_file = f.name

        try:
            start_time = time.time()

            with open(temp_file, 'rb') as f:
                files = {'file': f}
                response = requests.post(
                    f"{self.base_url}/api/analyze/file",
                    files=files,
                    timeout=300
                )

            upload_time = time.time() - start_time

            return {
                'file_size_mb': file_size_mb,
                'upload_time': upload_time,
                'status_code': response.status_code,
                'success': response.status_code < 400
            }

        except Exception as e:
            return {
                'file_size_mb': file_size_mb,
                'error': str(e),
                'success': False
            }

    def _calculate_stats(self, times: List[float], errors: int, total_time: float, num_requests: int, status_codes: Dict) -> Dict:
        """Calculate statistics from test results"""
        if not times:
            return {
                'error': 'No successful requests',
                'total_requests': num_requests,
                'errors': errors
            }

        avg_time = statistics.mean(times)
        median_time = statistics.median(times)
        min_time = min(times)
        max_time = max(times)
        stddev = statistics.stdev(times) if len(times) > 1 else 0
        p95 = self._percentile(times, 95)
        p99 = self._percentile(times, 99)

        requests_per_second = num_requests / total_time

        stats = {
            'total_requests': num_requests,
            'successful_requests': num_requests - errors,
            'failed_requests': errors,
            'success_rate': (num_requests - errors) / num_requests * 100,
            'total_time_seconds': total_time,
            'requests_per_second': requests_per_second,
            'response_times': {
                'avg_ms': avg_time * 1000,
                'median_ms': median_time * 1000,
                'min_ms': min_time * 1000,
                'max_ms': max_time * 1000,
                'stddev_ms': stddev * 1000,
                'p95_ms': p95 * 1000,
                'p99_ms': p99 * 1000
            },
            'status_codes': status_codes
        }

        self._print_stats(stats)
        return stats

    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile"""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def _print_stats(self, stats: Dict):
        """Print statistics in readable format"""
        print(f"\n{'='*60}")
        print("RESULTS")
        print(f"{'='*60}")
        print(f"Total Requests:      {stats['total_requests']}")
        print(f"Successful:          {stats['successful_requests']}")
        print(f"Failed:              {stats['failed_requests']}")
        print(f"Success Rate:        {stats['success_rate']:.2f}%")
        print(f"Total Time:          {stats['total_time_seconds']:.2f}s")
        print(f"Requests/Second:     {stats['requests_per_second']:.2f}")
        print(f"\nResponse Times:")
        print(f"  Average:           {stats['response_times']['avg_ms']:.2f}ms")
        print(f"  Median:            {stats['response_times']['median_ms']:.2f}ms")
        print(f"  Min:               {stats['response_times']['min_ms']:.2f}ms")
        print(f"  Max:               {stats['response_times']['max_ms']:.2f}ms")
        print(f"  Std Dev:           {stats['response_times']['stddev_ms']:.2f}ms")
        print(f"  95th percentile:   {stats['response_times']['p95_ms']:.2f}ms")
        print(f"  99th percentile:   {stats['response_times']['p99_ms']:.2f}ms")
        print(f"\nStatus Codes:")
        for code, count in sorted(stats['status_codes'].items()):
            print(f"  {code}: {count}")
        print(f"{'='*60}")

    def save_results(self, filename: str):
        """Save test results to JSON file"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'tests': self.results
        }

        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\nResults saved to {filename}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Load testing utility')
    parser.add_argument('--url', default='http://localhost:8000', help='Base URL')
    parser.add_argument('--requests', type=int, default=100, help='Number of requests')
    parser.add_argument('--workers', type=int, default=10, help='Concurrent workers')
    parser.add_argument('--test-type', choices=['sequential', 'concurrent', 'async'], default='concurrent')
    parser.add_argument('--endpoint', default='/api/health', help='Endpoint to test')
    parser.add_argument('--output', help='Output file for results')

    args = parser.parse_args()

    tester = LoadTester(base_url=args.url)

    print(f"\nLoad Testing Configuration:")
    print(f"  Base URL: {args.url}")
    print(f"  Endpoint: {args.endpoint}")
    print(f"  Requests: {args.requests}")
    print(f"  Test Type: {args.test_type}")

    if args.test_type == 'sequential':
        results = tester.run_sequential_test(args.endpoint, args.requests)
    elif args.test_type == 'concurrent':
        results = tester.run_concurrent_test(args.endpoint, args.requests, args.workers)
    elif args.test_type == 'async':
        results = asyncio.run(tester.run_async_test(args.endpoint, args.requests, args.workers))

    tester.results.append({
        'test_type': args.test_type,
        'endpoint': args.endpoint,
        'results': results
    })

    if args.output:
        tester.save_results(args.output)


if __name__ == '__main__':
    main()
