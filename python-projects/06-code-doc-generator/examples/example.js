/**
 * Example JavaScript module for testing code documentation generator.
 *
 * This module demonstrates various JavaScript/ES6 constructs including
 * classes, async functions, arrow functions, and modern syntax.
 *
 * @module example
 */

/**
 * User management class with authentication capabilities.
 */
class UserManager {
    /**
     * Create a new UserManager instance.
     *
     * @param {Object} database - Database connection object
     */
    constructor(database) {
        this.db = database;
        this.users = new Map();
        this.sessionTimeout = 3600000; // 1 hour in milliseconds
    }

    /**
     * Create a new user account.
     *
     * @async
     * @param {string} username - Username for the new account
     * @param {string} email - Email address
     * @param {string} password - Password (will be hashed)
     * @returns {Promise<Object>} Created user object
     * @throws {Error} If username or email already exists
     */
    async createUser(username, email, password) {
        // Validate input
        if (!username || !email || !password) {
            throw new Error('Missing required fields');
        }

        // Check for existing user
        const existing = await this.findUserByEmail(email);
        if (existing) {
            throw new Error('Email already registered');
        }

        // Create user object
        const user = {
            id: this.generateId(),
            username: username,
            email: email,
            passwordHash: await this.hashPassword(password),
            createdAt: new Date(),
            lastLogin: null,
            active: true
        };

        // Save to database
        await this.db.save('users', user);
        this.users.set(user.id, user);

        return user;
    }

    /**
     * Authenticate a user with email and password.
     *
     * @async
     * @param {string} email - User's email
     * @param {string} password - User's password
     * @returns {Promise<Object|null>} User object if authenticated, null otherwise
     */
    async authenticate(email, password) {
        const user = await this.findUserByEmail(email);

        if (!user || !user.active) {
            return null;
        }

        const isValid = await this.verifyPassword(password, user.passwordHash);

        if (isValid) {
            user.lastLogin = new Date();
            await this.db.update('users', user.id, { lastLogin: user.lastLogin });
            return user;
        }

        return null;
    }

    /**
     * Find user by email address.
     *
     * @async
     * @param {string} email - Email to search for
     * @returns {Promise<Object|null>} User object or null
     */
    async findUserByEmail(email) {
        return await this.db.findOne('users', { email: email });
    }

    /**
     * Generate a unique user ID.
     *
     * @private
     * @returns {string} Unique identifier
     */
    generateId() {
        return Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
    }

    /**
     * Hash a password using bcrypt (simulated).
     *
     * @async
     * @private
     * @param {string} password - Plain text password
     * @returns {Promise<string>} Hashed password
     */
    async hashPassword(password) {
        // In real implementation, use bcrypt or similar
        return `hashed_${password}_${Date.now()}`;
    }

    /**
     * Verify password against hash.
     *
     * @async
     * @private
     * @param {string} password - Plain text password
     * @param {string} hash - Password hash
     * @returns {Promise<boolean>} True if password matches
     */
    async verifyPassword(password, hash) {
        // Simplified verification
        return hash.includes(password);
    }
}


/**
 * Task queue for managing asynchronous operations.
 */
class TaskQueue {
    /**
     * Initialize task queue.
     *
     * @param {number} concurrency - Maximum concurrent tasks
     */
    constructor(concurrency = 5) {
        this.concurrency = concurrency;
        this.running = 0;
        this.queue = [];
    }

    /**
     * Add a task to the queue.
     *
     * @async
     * @param {Function} taskFn - Async function to execute
     * @param {...any} args - Arguments for the task function
     * @returns {Promise<any>} Task result
     */
    async enqueue(taskFn, ...args) {
        return new Promise((resolve, reject) => {
            this.queue.push({
                taskFn,
                args,
                resolve,
                reject
            });

            this.processQueue();
        });
    }

    /**
     * Process tasks from queue.
     *
     * @private
     * @async
     */
    async processQueue() {
        if (this.running >= this.concurrency || this.queue.length === 0) {
            return;
        }

        this.running++;
        const { taskFn, args, resolve, reject } = this.queue.shift();

        try {
            const result = await taskFn(...args);
            resolve(result);
        } catch (error) {
            reject(error);
        } finally {
            this.running--;
            this.processQueue();
        }
    }
}


/**
 * Utility functions for data manipulation.
 */
const DataUtils = {
    /**
     * Calculate average of an array of numbers.
     *
     * @param {number[]} numbers - Array of numbers
     * @returns {number} Average value
     */
    average: (numbers) => {
        if (!numbers || numbers.length === 0) {
            return 0;
        }
        return numbers.reduce((sum, num) => sum + num, 0) / numbers.length;
    },

    /**
     * Find median value in array.
     *
     * @param {number[]} numbers - Array of numbers
     * @returns {number} Median value
     */
    median: (numbers) => {
        if (!numbers || numbers.length === 0) {
            return 0;
        }

        const sorted = [...numbers].sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);

        return sorted.length % 2 === 0
            ? (sorted[mid - 1] + sorted[mid]) / 2
            : sorted[mid];
    },

    /**
     * Remove duplicate values from array.
     *
     * @param {Array} array - Input array
     * @returns {Array} Array without duplicates
     */
    unique: (array) => {
        return [...new Set(array)];
    },

    /**
     * Group array elements by a key function.
     *
     * @param {Array} array - Input array
     * @param {Function} keyFn - Function to extract grouping key
     * @returns {Object} Object with grouped elements
     */
    groupBy: (array, keyFn) => {
        return array.reduce((groups, item) => {
            const key = keyFn(item);
            if (!groups[key]) {
                groups[key] = [];
            }
            groups[key].push(item);
            return groups;
        }, {});
    }
};


/**
 * Retry a function with exponential backoff.
 *
 * @async
 * @param {Function} fn - Async function to retry
 * @param {number} maxRetries - Maximum number of retry attempts
 * @param {number} delay - Initial delay in milliseconds
 * @returns {Promise<any>} Function result
 * @throws {Error} If all retries fail
 */
async function retryWithBackoff(fn, maxRetries = 3, delay = 1000) {
    let lastError;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            return await fn();
        } catch (error) {
            lastError = error;

            if (attempt < maxRetries) {
                const waitTime = delay * Math.pow(2, attempt);
                console.log(`Retry attempt ${attempt + 1} after ${waitTime}ms`);
                await new Promise(resolve => setTimeout(resolve, waitTime));
            }
        }
    }

    throw new Error(`Failed after ${maxRetries} retries: ${lastError.message}`);
}


/**
 * Debounce a function call.
 *
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
function debounce(func, wait) {
    let timeout;

    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };

        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}


/**
 * Throttle a function call.
 *
 * @param {Function} func - Function to throttle
 * @param {number} limit - Time limit in milliseconds
 * @returns {Function} Throttled function
 */
function throttle(func, limit) {
    let inThrottle;

    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}


/**
 * Deep clone an object.
 *
 * @param {Object} obj - Object to clone
 * @returns {Object} Cloned object
 */
function deepClone(obj) {
    if (obj === null || typeof obj !== 'object') {
        return obj;
    }

    if (obj instanceof Date) {
        return new Date(obj.getTime());
    }

    if (obj instanceof Array) {
        return obj.map(item => deepClone(item));
    }

    if (obj instanceof Object) {
        const clonedObj = {};
        for (const key in obj) {
            if (obj.hasOwnProperty(key)) {
                clonedObj[key] = deepClone(obj[key]);
            }
        }
        return clonedObj;
    }
}


// Export for Node.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        UserManager,
        TaskQueue,
        DataUtils,
        retryWithBackoff,
        debounce,
        throttle,
        deepClone
    };
}
