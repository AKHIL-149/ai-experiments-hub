"""
Tests for Java Parser
"""
import pytest
from src.parsers.java_parser import JavaParser
from src.parsers.base_parser import ParseError


@pytest.fixture
def parser():
    """Create JavaParser instance"""
    return JavaParser()


class TestJavaParserBasics:
    """Test basic Java parsing functionality"""

    def test_supported_extensions(self, parser):
        """Test supported file extensions"""
        assert '.java' in parser.supported_extensions

    def test_can_parse_java_file(self, parser):
        """Test can_parse method"""
        assert parser.can_parse('Test.java')
        assert parser.can_parse('com/example/MyClass.java')
        assert not parser.can_parse('test.py')
        assert not parser.can_parse('test.js')

    def test_parse_empty_code(self, parser):
        """Test parsing empty code"""
        code = ""
        result = parser.parse_code(code, 'Empty.java')
        assert result.language == 'java'
        assert result.file_path == 'Empty.java'
        assert len(result.functions) == 0
        assert len(result.classes) == 0


class TestJavaClassParsing:
    """Test Java class parsing"""

    def test_parse_simple_class(self, parser):
        """Test parsing simple class"""
        code = """
        package com.example;

        public class HelloWorld {
            private String message;

            public void sayHello() {
                System.out.println("Hello!");
            }
        }
        """
        result = parser.parse_code(code, 'HelloWorld.java')
        assert result.language == 'java'
        assert len(result.classes) >= 1

        cls = result.classes[0]
        assert 'HelloWorld' in cls.name
        assert len(cls.methods) >= 1
        assert any('sayHello' in m.name for m in cls.methods)

    def test_parse_class_with_inheritance(self, parser):
        """Test parsing class with extends"""
        code = """
        public class Dog extends Animal {
            public void bark() {
                System.out.println("Woof!");
            }
        }
        """
        result = parser.parse_code(code, 'Dog.java')
        assert len(result.classes) >= 1

        cls = result.classes[0]
        assert 'Dog' in cls.name
        assert 'Animal' in cls.base_classes

    def test_parse_class_with_interface(self, parser):
        """Test parsing class implementing interface"""
        code = """
        public class MyList implements List, Serializable {
            public int size() {
                return 0;
            }
        }
        """
        result = parser.parse_code(code, 'MyList.java')
        assert len(result.classes) >= 1

        cls = result.classes[0]
        assert 'MyList' in cls.name
        # Should have interfaces in base_classes
        assert len(cls.base_classes) >= 1

    def test_parse_interface(self, parser):
        """Test parsing interface"""
        code = """
        public interface Runnable {
            void run();
            default void start() {
                System.out.println("Starting");
            }
        }
        """
        result = parser.parse_code(code, 'Runnable.java')
        assert len(result.classes) >= 1

        interface = result.classes[0]
        assert 'Runnable' in interface.name
        assert 'interface' in interface.name.lower()

    def test_parse_enum(self, parser):
        """Test parsing enum"""
        code = """
        public enum Day {
            MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY;

            public boolean isWeekend() {
                return this == SATURDAY || this == SUNDAY;
            }
        }
        """
        result = parser.parse_code(code, 'Day.java')
        assert len(result.classes) >= 1

        enum = result.classes[0]
        assert 'Day' in enum.name
        assert 'enum' in enum.name.lower()


class TestJavaMethodParsing:
    """Test Java method parsing"""

    def test_parse_simple_method(self, parser):
        """Test parsing simple method"""
        code = """
        public class Calculator {
            public int add(int a, int b) {
                return a + b;
            }
        }
        """
        result = parser.parse_code(code, 'Calculator.java')
        assert len(result.classes) >= 1

        cls = result.classes[0]
        assert len(cls.methods) >= 1

        method = cls.methods[0]
        assert 'add' in method.name
        assert len(method.parameters) == 2
        assert method.return_type == 'int'

    def test_parse_method_with_void_return(self, parser):
        """Test parsing method with void return"""
        code = """
        public class Printer {
            public void print(String text) {
                System.out.println(text);
            }
        }
        """
        result = parser.parse_code(code, 'Printer.java')
        cls = result.classes[0]
        method = cls.methods[0]

        assert 'print' in method.name
        assert method.return_type == 'void'
        assert len(method.parameters) == 1

    def test_parse_static_method(self, parser):
        """Test parsing static method"""
        code = """
        public class Utils {
            public static int max(int a, int b) {
                return a > b ? a : b;
            }
        }
        """
        result = parser.parse_code(code, 'Utils.java')
        cls = result.classes[0]
        method = cls.methods[0]

        assert 'max' in method.name
        assert method.is_static == True

    def test_parse_constructor(self, parser):
        """Test parsing constructor"""
        code = """
        public class Person {
            private String name;

            public Person(String name) {
                this.name = name;
            }
        }
        """
        result = parser.parse_code(code, 'Person.java')
        cls = result.classes[0]

        # Constructor should be in methods
        assert len(cls.methods) >= 1
        constructor = cls.methods[0]
        assert 'Person' in constructor.name
        assert 'constructor' in constructor.name.lower()

    def test_parse_method_with_annotations(self, parser):
        """Test parsing method with annotations"""
        code = """
        public class Service {
            @Override
            @Deprecated
            public void oldMethod() {
                // deprecated
            }
        }
        """
        result = parser.parse_code(code, 'Service.java')
        cls = result.classes[0]
        method = cls.methods[0]

        assert len(method.decorators) >= 1
        assert any('@Override' in d for d in method.decorators)


class TestJavaGenerics:
    """Test Java generic type parsing"""

    def test_parse_generic_class(self, parser):
        """Test parsing generic class"""
        code = """
        public class Box<T> {
            private T value;

            public T getValue() {
                return value;
            }

            public void setValue(T value) {
                this.value = value;
            }
        }
        """
        result = parser.parse_code(code, 'Box.java')
        assert len(result.classes) >= 1

    def test_parse_generic_method(self, parser):
        """Test parsing generic method"""
        code = """
        public class Utils {
            public static <T> T getFirst(List<T> list) {
                return list.get(0);
            }
        }
        """
        result = parser.parse_code(code, 'Utils.java')
        assert len(result.classes) >= 1


class TestJavaPackageImports:
    """Test package and import parsing"""

    def test_parse_package(self, parser):
        """Test parsing package declaration"""
        code = """
        package com.example.myapp;

        public class App {
            public static void main(String[] args) {
                System.out.println("Hello");
            }
        }
        """
        result = parser.parse_code(code, 'App.java')
        # Package info is parsed but not directly exposed in ParsedModule
        assert len(result.classes) >= 1

    def test_parse_imports(self, parser):
        """Test parsing import statements"""
        code = """
        import java.util.List;
        import java.util.ArrayList;
        import java.io.*;

        public class MyClass {
            private List<String> items = new ArrayList<>();
        }
        """
        result = parser.parse_code(code, 'MyClass.java')
        assert len(result.imports) >= 2
        assert 'java.util.List' in result.imports or any('List' in imp for imp in result.imports)


class TestJavaDocParsing:
    """Test Javadoc comment parsing"""

    def test_parse_class_javadoc(self, parser):
        """Test parsing class-level Javadoc"""
        code = """
        /**
         * This is a Calculator class.
         * It performs basic arithmetic operations.
         */
        public class Calculator {
            public int add(int a, int b) {
                return a + b;
            }
        }
        """
        result = parser.parse_code(code, 'Calculator.java')
        cls = result.classes[0]

        # Javadoc should be extracted
        assert cls.docstring is not None
        assert 'Calculator' in cls.docstring or 'arithmetic' in cls.docstring.lower()

    def test_parse_method_javadoc(self, parser):
        """Test parsing method-level Javadoc"""
        code = """
        public class Math {
            /**
             * Adds two numbers together.
             * @param a first number
             * @param b second number
             * @return sum of a and b
             */
            public int add(int a, int b) {
                return a + b;
            }
        }
        """
        result = parser.parse_code(code, 'Math.java')
        cls = result.classes[0]
        method = cls.methods[0]

        # Method Javadoc should be extracted
        assert method.docstring is not None
        assert 'add' in method.docstring.lower() or 'sum' in method.docstring.lower()


class TestJavaComplexScenarios:
    """Test complex Java code scenarios"""

    def test_parse_nested_classes(self, parser):
        """Test parsing nested classes"""
        code = """
        public class Outer {
            private String name;

            public class Inner {
                public void printName() {
                    System.out.println(name);
                }
            }

            public static class StaticNested {
                public void hello() {
                    System.out.println("Hello");
                }
            }
        }
        """
        result = parser.parse_code(code, 'Outer.java')
        # Should parse at least the outer class
        assert len(result.classes) >= 1

    def test_parse_spring_annotations(self, parser):
        """Test parsing Spring Boot annotations"""
        code = """
        import org.springframework.web.bind.annotation.*;

        @RestController
        @RequestMapping("/api")
        public class UserController {

            @GetMapping("/users")
            public List<User> getUsers() {
                return userService.findAll();
            }

            @PostMapping("/users")
            public User createUser(@RequestBody User user) {
                return userService.save(user);
            }
        }
        """
        result = parser.parse_code(code, 'UserController.java')
        assert len(result.classes) >= 1

        cls = result.classes[0]
        assert len(cls.decorators) >= 1
        assert any('@RestController' in d for d in cls.decorators)

    def test_parse_exception_handling(self, parser):
        """Test parsing exception handling"""
        code = """
        public class FileReader {
            public String readFile(String path) throws IOException {
                try {
                    return Files.readString(Path.of(path));
                } catch (IOException e) {
                    throw new RuntimeException("Failed to read file", e);
                }
            }
        }
        """
        result = parser.parse_code(code, 'FileReader.java')
        assert len(result.classes) >= 1

    def test_parse_lambda_expressions(self, parser):
        """Test parsing lambda expressions"""
        code = """
        public class Lambdas {
            public void test() {
                List<String> names = Arrays.asList("Alice", "Bob");
                names.forEach(name -> System.out.println(name));

                Comparator<String> comp = (a, b) -> a.compareTo(b);
            }
        }
        """
        result = parser.parse_code(code, 'Lambdas.java')
        assert len(result.classes) >= 1


class TestJavaFallbackParser:
    """Test regex-based fallback parser"""

    def test_fallback_parse_class(self, parser):
        """Test fallback parser can parse basic class"""
        code = """
        public class Simple {
            public void method() {
                System.out.println("Hello");
            }
        }
        """
        # Force fallback by using _parse_with_regex
        result = parser._parse_with_regex(code, 'Simple.java')
        assert result.language == 'java'
        assert len(result.classes) >= 1

    def test_fallback_parse_interface(self, parser):
        """Test fallback parser can parse interface"""
        code = """
        public interface MyInterface {
            void doSomething();
        }
        """
        result = parser._parse_with_regex(code, 'MyInterface.java')
        assert len(result.classes) >= 1
        interface = result.classes[0]
        assert 'interface' in interface.name.lower()

    def test_fallback_parse_enum(self, parser):
        """Test fallback parser can parse enum"""
        code = """
        public enum Color {
            RED, GREEN, BLUE
        }
        """
        result = parser._parse_with_regex(code, 'Color.java')
        assert len(result.classes) >= 1
        enum = result.classes[0]
        assert 'enum' in enum.name.lower()


class TestJavaEdgeCases:
    """Test edge cases"""

    def test_parse_abstract_class(self, parser):
        """Test parsing abstract class"""
        code = """
        public abstract class Animal {
            protected String name;

            public abstract void makeSound();

            public void sleep() {
                System.out.println("Zzz");
            }
        }
        """
        result = parser.parse_code(code, 'Animal.java')
        assert len(result.classes) >= 1

    def test_parse_final_class(self, parser):
        """Test parsing final class"""
        code = """
        public final class Constants {
            public static final int MAX_SIZE = 100;

            private Constants() {
                // prevent instantiation
            }
        }
        """
        result = parser.parse_code(code, 'Constants.java')
        assert len(result.classes) >= 1

    def test_parse_multiline_string(self, parser):
        """Test parsing with multiline strings"""
        code = """
        public class MultiLine {
            public void test() {
                String text = "Line 1" +
                              "Line 2" +
                              "Line 3";
            }
        }
        """
        result = parser.parse_code(code, 'MultiLine.java')
        assert len(result.classes) >= 1

    def test_parse_array_types(self, parser):
        """Test parsing array types"""
        code = """
        public class Arrays {
            private int[] numbers;
            private String[][] matrix;

            public int[] getNumbers() {
                return numbers;
            }
        }
        """
        result = parser.parse_code(code, 'Arrays.java')
        assert len(result.classes) >= 1
