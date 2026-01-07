"""Example Python module for testing code documentation generator.

This module demonstrates various Python constructs including classes,
functions, decorators, type hints, and different complexity levels.
"""

from typing import List, Optional, Dict, Tuple
from functools import wraps
import time


def timer_decorator(func):
    """Decorator that measures function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        print(f"{func.__name__} took {end - start:.2f} seconds")
        return result
    return wrapper


class DataProcessor:
    """Process and analyze data with various operations.

    This class provides methods for data transformation, validation,
    and statistical analysis.
    """

    def __init__(self, data: List[float], name: str = "default"):
        """Initialize the DataProcessor.

        Args:
            data: List of numeric values to process
            name: Optional name for the processor instance
        """
        self.data = data
        self.name = name
        self._cache = {}

    def calculate_statistics(self) -> Dict[str, float]:
        """Calculate basic statistics for the data.

        Returns:
            Dictionary containing mean, median, min, max, and std deviation
        """
        if not self.data:
            return {}

        sorted_data = sorted(self.data)
        n = len(sorted_data)

        stats = {
            'count': n,
            'sum': sum(self.data),
            'mean': sum(self.data) / n,
            'min': min(self.data),
            'max': max(self.data),
            'median': sorted_data[n // 2] if n % 2 else (sorted_data[n // 2 - 1] + sorted_data[n // 2]) / 2
        }

        # Calculate standard deviation
        mean = stats['mean']
        variance = sum((x - mean) ** 2 for x in self.data) / n
        stats['std_dev'] = variance ** 0.5

        return stats

    @timer_decorator
    def filter_outliers(self, threshold: float = 2.0) -> List[float]:
        """Remove outliers using standard deviation method.

        Args:
            threshold: Number of standard deviations to use as cutoff

        Returns:
            Filtered list without outliers
        """
        stats = self.calculate_statistics()
        mean = stats['mean']
        std_dev = stats['std_dev']

        lower_bound = mean - (threshold * std_dev)
        upper_bound = mean + (threshold * std_dev)

        return [x for x in self.data if lower_bound <= x <= upper_bound]

    def normalize(self, method: str = "minmax") -> List[float]:
        """Normalize data using specified method.

        Args:
            method: Normalization method ('minmax' or 'zscore')

        Returns:
            Normalized data

        Raises:
            ValueError: If method is not supported
        """
        if method == "minmax":
            min_val = min(self.data)
            max_val = max(self.data)
            range_val = max_val - min_val

            if range_val == 0:
                return [0.0] * len(self.data)

            return [(x - min_val) / range_val for x in self.data]

        elif method == "zscore":
            stats = self.calculate_statistics()
            mean = stats['mean']
            std_dev = stats['std_dev']

            if std_dev == 0:
                return [0.0] * len(self.data)

            return [(x - mean) / std_dev for x in self.data]

        else:
            raise ValueError(f"Unsupported normalization method: {method}")


class FileHandler:
    """Handle file operations with error handling."""

    @staticmethod
    def read_numbers_from_file(filepath: str) -> List[float]:
        """Read numeric values from a text file.

        Args:
            filepath: Path to the file

        Returns:
            List of numbers read from file
        """
        numbers = []

        try:
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            numbers.append(float(line))
                        except ValueError:
                            print(f"Skipping invalid number: {line}")
        except FileNotFoundError:
            print(f"File not found: {filepath}")
        except PermissionError:
            print(f"Permission denied: {filepath}")

        return numbers

    @staticmethod
    def write_results(filepath: str, data: Dict[str, any]) -> bool:
        """Write results to a file.

        Args:
            filepath: Path to output file
            data: Dictionary of results to write

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, 'w') as f:
                for key, value in data.items():
                    f.write(f"{key}: {value}\n")
            return True
        except Exception as e:
            print(f"Error writing file: {e}")
            return False


def fibonacci(n: int) -> List[int]:
    """Generate Fibonacci sequence up to n terms.

    Args:
        n: Number of terms to generate

    Returns:
        List containing Fibonacci sequence

    Examples:
        >>> fibonacci(5)
        [0, 1, 1, 2, 3]
        >>> fibonacci(1)
        [0]
    """
    if n <= 0:
        return []
    elif n == 1:
        return [0]

    sequence = [0, 1]
    for i in range(2, n):
        sequence.append(sequence[i - 1] + sequence[i - 2])

    return sequence


def find_prime_numbers(limit: int) -> List[int]:
    """Find all prime numbers up to a given limit using Sieve of Eratosthenes.

    Args:
        limit: Upper bound for prime search (inclusive)

    Returns:
        List of prime numbers
    """
    if limit < 2:
        return []

    # Initialize sieve
    is_prime = [True] * (limit + 1)
    is_prime[0] = is_prime[1] = False

    # Sieve of Eratosthenes algorithm
    for i in range(2, int(limit ** 0.5) + 1):
        if is_prime[i]:
            for j in range(i * i, limit + 1, i):
                is_prime[j] = False

    return [num for num in range(limit + 1) if is_prime[num]]


def main():
    """Main execution function demonstrating the module usage."""
    print("=== Data Processing Example ===\n")

    # Create sample data
    data = [1.2, 2.3, 3.4, 4.5, 5.6, 100.0, 6.7, 7.8, 8.9, 9.0]

    # Initialize processor
    processor = DataProcessor(data, name="example")

    # Calculate statistics
    stats = processor.calculate_statistics()
    print("Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value:.2f}")

    # Filter outliers
    print("\nFiltering outliers...")
    filtered = processor.filter_outliers(threshold=2.0)
    print(f"Original count: {len(data)}")
    print(f"Filtered count: {len(filtered)}")

    # Normalize data
    print("\nNormalizing data...")
    normalized = processor.normalize(method="minmax")
    print(f"Normalized range: {min(normalized):.2f} to {max(normalized):.2f}")

    # Generate Fibonacci
    print("\nFibonacci sequence (10 terms):")
    fib = fibonacci(10)
    print(fib)

    # Find primes
    print("\nPrime numbers up to 50:")
    primes = find_prime_numbers(50)
    print(primes)


if __name__ == "__main__":
    main()
