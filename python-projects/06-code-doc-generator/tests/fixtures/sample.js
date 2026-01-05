/**
 * Sample JavaScript module for testing the parser
 *
 * This module contains various JavaScript/ES6+ constructs to test
 * the parser's ability to extract functions, classes, and imports.
 */

// Imports
import { useState, useEffect } from 'react';
import axios from 'axios';
import * as Utils from './utils';

// Constants
const API_URL = 'https://api.example.com';
const MAX_RETRIES = 3;
let globalCounter = 0;

/**
 * A simple function with JSDoc documentation
 * @param {string} name - The name to greet
 * @returns {string} A greeting message
 */
function greet(name) {
    return `Hello, ${name}!`;
}

/**
 * Async function for fetching data
 * @param {string} url - The URL to fetch from
 * @param {number} timeout - Request timeout in milliseconds
 * @returns {Promise<Object>} The fetched data
 */
async function fetchData(url, timeout = 5000) {
    try {
        const response = await axios.get(url, { timeout });
        return response.data;
    } catch (error) {
        console.error('Failed to fetch:', error);
        throw error;
    }
}

/**
 * Arrow function example
 */
const processArray = (arr, callback) => {
    return arr.map(callback).filter(x => x !== null);
};

/**
 * Function with default parameters and rest args
 * @param {number} x - First number
 * @param {number} y - Second number (default: 10)
 * @param {...number} rest - Additional numbers
 * @returns {number} Sum of all numbers
 */
function sumNumbers(x, y = 10, ...rest) {
    let sum = x + y;
    for (const num of rest) {
        sum += num;
    }
    return sum;
}

/**
 * Simple class example
 */
class Person {
    /**
     * Create a person
     * @param {string} name - Person's name
     * @param {number} age - Person's age
     */
    constructor(name, age) {
        this.name = name;
        this.age = age;
    }

    /**
     * Get person's greeting
     * @returns {string} Greeting message
     */
    greet() {
        return `Hi, I'm ${this.name} and I'm ${this.age} years old`;
    }

    /**
     * Static utility method
     * @param {Object} data - Person data
     * @returns {Person} New person instance
     */
    static fromObject(data) {
        return new Person(data.name, data.age);
    }

    /**
     * Getter for birth year (approximate)
     */
    get birthYear() {
        const currentYear = new Date().getFullYear();
        return currentYear - this.age;
    }
}

/**
 * Class with inheritance
 */
class Employee extends Person {
    /**
     * Create an employee
     * @param {string} name - Employee name
     * @param {number} age - Employee age
     * @param {string} company - Company name
     */
    constructor(name, age, company) {
        super(name, age);
        this.company = company;
    }

    /**
     * Get employee info
     * @returns {string} Employee details
     */
    getInfo() {
        return `${this.greet()} and I work at ${this.company}`;
    }

    /**
     * Async method example
     * @param {string} taskId - Task identifier
     * @returns {Promise<Object>} Task result
     */
    async performTask(taskId) {
        const task = await fetchData(`${API_URL}/tasks/${taskId}`);
        return task;
    }
}

/**
 * Modern class with class fields
 */
class Counter {
    // Class fields (ES2022)
    count = 0;
    static instances = 0;

    constructor() {
        Counter.instances++;
    }

    increment() {
        this.count++;
    }

    static getInstances() {
        return Counter.instances;
    }
}

// Export examples
export { greet, fetchData };
export default Person;
