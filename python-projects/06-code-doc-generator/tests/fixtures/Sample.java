/**
 * Sample Java file for testing the parser
 *
 * This file demonstrates various Java language features including
 * classes, interfaces, enums, and different method types.
 */
package com.example.demo;

import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;

/**
 * A simple Person class demonstrating basic Java features
 */
public class Person {
    // Instance variables
    private String name;
    private int age;
    protected String email;

    // Static variable
    public static int instanceCount = 0;

    /**
     * Default constructor
     */
    public Person() {
        this("Unknown", 0);
    }

    /**
     * Parameterized constructor
     * @param name Person's name
     * @param age Person's age
     */
    public Person(String name, int age) {
        this.name = name;
        this.age = age;
        instanceCount++;
    }

    /**
     * Get the person's name
     * @return The person's name
     */
    public String getName() {
        return name;
    }

    /**
     * Set the person's name
     * @param name The new name
     */
    public void setName(String name) {
        this.name = name;
    }

    /**
     * Get the person's age
     * @return The person's age
     */
    public int getAge() {
        return age;
    }

    /**
     * Calculate birth year
     * @param currentYear The current year
     * @return Approximate birth year
     */
    public int calculateBirthYear(int currentYear) {
        return currentYear - age;
    }

    /**
     * Static utility method
     * @param data Map containing person data
     * @return New Person instance
     */
    public static Person fromMap(Map<String, Object> data) {
        String name = (String) data.get("name");
        Integer age = (Integer) data.get("age");
        return new Person(name, age != null ? age : 0);
    }

    @Override
    public String toString() {
        return String.format("Person{name='%s', age=%d}", name, age);
    }
}

/**
 * Employee class demonstrating inheritance
 */
class Employee extends Person {
    private String company;
    private double salary;

    /**
     * Constructor for Employee
     * @param name Employee name
     * @param age Employee age
     * @param company Company name
     */
    public Employee(String name, int age, String company) {
        super(name, age);
        this.company = company;
    }

    /**
     * Get company name
     * @return The company name
     */
    public String getCompany() {
        return company;
    }

    /**
     * Set salary
     * @param salary The new salary
     */
    public void setSalary(double salary) {
        this.salary = salary;
    }

    /**
     * Calculate annual bonus
     * @param percentage Bonus percentage (0-100)
     * @return Bonus amount
     */
    public double calculateBonus(double percentage) {
        return salary * (percentage / 100.0);
    }

    @Override
    public String toString() {
        return String.format("Employee{name='%s', age=%d, company='%s'}",
                           getName(), getAge(), company);
    }
}

/**
 * Demonstrating an interface
 */
interface Payable {
    /**
     * Calculate payment amount
     * @return Payment amount
     */
    double calculatePayment();

    /**
     * Process payment
     * @return true if payment was successful
     */
    boolean processPayment();
}

/**
 * Contractor class implementing an interface
 */
class Contractor extends Person implements Payable {
    private double hourlyRate;
    private int hoursWorked;

    /**
     * Constructor
     * @param name Contractor name
     * @param age Contractor age
     * @param hourlyRate Rate per hour
     */
    public Contractor(String name, int age, double hourlyRate) {
        super(name, age);
        this.hourlyRate = hourlyRate;
        this.hoursWorked = 0;
    }

    /**
     * Log hours worked
     * @param hours Number of hours
     */
    public void logHours(int hours) {
        this.hoursWorked += hours;
    }

    @Override
    public double calculatePayment() {
        return hourlyRate * hoursWorked;
    }

    @Override
    public boolean processPayment() {
        double amount = calculatePayment();
        if (amount > 0) {
            hoursWorked = 0; // Reset after payment
            return true;
        }
        return false;
    }
}

/**
 * Enum for employment status
 */
enum EmploymentStatus {
    FULL_TIME,
    PART_TIME,
    CONTRACT,
    INTERN,
    TERMINATED
}

/**
 * Utility class with static methods only
 */
final class PersonUtils {
    // Private constructor to prevent instantiation
    private PersonUtils() {
        throw new AssertionError("Cannot instantiate utility class");
    }

    /**
     * Validate person's age
     * @param age Age to validate
     * @return true if age is valid
     */
    public static boolean isValidAge(int age) {
        return age >= 0 && age <= 150;
    }

    /**
     * Format person name
     * @param firstName First name
     * @param lastName Last name
     * @return Formatted full name
     */
    public static String formatName(String firstName, String lastName) {
        return String.format("%s %s", firstName, lastName);
    }
}

/**
 * Abstract class demonstrating abstraction
 */
abstract class Animal {
    protected String species;

    /**
     * Constructor
     * @param species Animal species
     */
    public Animal(String species) {
        this.species = species;
    }

    /**
     * Abstract method to be implemented by subclasses
     * @return The sound the animal makes
     */
    public abstract String makeSound();

    /**
     * Concrete method
     * @return Species name
     */
    public String getSpecies() {
        return species;
    }
}
