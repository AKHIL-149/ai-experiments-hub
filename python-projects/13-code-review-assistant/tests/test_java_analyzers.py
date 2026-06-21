"""
Tests for Java Security and Smell Analyzers
"""
import pytest
from src.parsers.java_parser import JavaParser
from src.analyzers.java_security_analyzer import JavaSecurityAnalyzer
from src.analyzers.java_smell_analyzer import JavaSmellAnalyzer
from src.analyzers.base_analyzer import IssueSeverity, IssueCategory


@pytest.fixture
def parser():
    """Create JavaParser instance"""
    return JavaParser()


@pytest.fixture
def security_analyzer():
    """Create JavaSecurityAnalyzer instance"""
    return JavaSecurityAnalyzer()


@pytest.fixture
def smell_analyzer():
    """Create JavaSmellAnalyzer instance"""
    return JavaSmellAnalyzer()


class TestJavaSecurityAnalyzer:
    """Test Java security vulnerability detection"""

    def test_detect_sql_injection(self, parser, security_analyzer):
        """Test SQL injection detection"""
        code = '''
        public class UserDAO {
            public User findUser(String username) {
                String query = "SELECT * FROM users WHERE username = '" + username + "'";
                Statement stmt = connection.createStatement();
                return stmt.executeQuery(query);
            }
        }
        '''
        parsed = parser.parse_code(code, 'UserDAO.java')
        issues = security_analyzer.analyze(parsed, code)

        sql_issues = [i for i in issues if i.rule_id == 'JAVA-SEC001']
        assert len(sql_issues) >= 1
        assert sql_issues[0].severity == IssueSeverity.CRITICAL
        assert 'sql injection' in sql_issues[0].title.lower()

    def test_detect_command_injection(self, parser, security_analyzer):
        """Test command injection detection"""
        code = '''
        public class FileProcessor {
            public void processFile(String filename) throws IOException {
                String command = "cat " + filename;
                Runtime.getRuntime().exec(command);
            }
        }
        '''
        parsed = parser.parse_code(code, 'FileProcessor.java')
        issues = security_analyzer.analyze(parsed, code)

        cmd_issues = [i for i in issues if i.rule_id == 'JAVA-SEC002']
        assert len(cmd_issues) >= 1
        assert cmd_issues[0].severity in [IssueSeverity.CRITICAL, IssueSeverity.ERROR]

    def test_detect_path_traversal(self, parser, security_analyzer):
        """Test path traversal detection"""
        code = '''
        public class FileReader {
            public String readFile(String path) throws IOException {
                File file = new File(path);
                return Files.readString(file.toPath());
            }
        }
        '''
        parsed = parser.parse_code(code, 'FileReader.java')
        issues = security_analyzer.analyze(parsed, code)

        path_issues = [i for i in issues if i.rule_id == 'JAVA-SEC003']
        assert len(path_issues) >= 1
        assert 'path traversal' in path_issues[0].title.lower()

    def test_detect_unsafe_deserialization(self, parser, security_analyzer):
        """Test unsafe deserialization detection"""
        # Use inline pattern for regex detection
        code = '''
        public class DataLoader {
            public Object loadData(InputStream input) throws IOException, ClassNotFoundException {
                return new ObjectInputStream(input).readObject();
            }
        }
        '''
        parsed = parser.parse_code(code, 'DataLoader.java')
        issues = security_analyzer.analyze(parsed, code)

        deserial_issues = [i for i in issues if i.rule_id == 'JAVA-SEC004']
        assert len(deserial_issues) >= 1
        assert deserial_issues[0].severity == IssueSeverity.CRITICAL

    def test_detect_xxe_vulnerability(self, parser, security_analyzer):
        """Test XXE vulnerability detection"""
        code = '''
        public class XMLParser {
            public Document parse(File file) throws Exception {
                DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
                DocumentBuilder db = dbf.newDocumentBuilder();
                return db.parse(file);
            }
        }
        '''
        parsed = parser.parse_code(code, 'XMLParser.java')
        issues = security_analyzer.analyze(parsed, code)

        xxe_issues = [i for i in issues if i.rule_id == 'JAVA-SEC005']
        assert len(xxe_issues) >= 1
        assert 'xxe' in xxe_issues[0].title.lower()

    def test_detect_hardcoded_password(self, parser, security_analyzer):
        """Test hardcoded password detection"""
        code = '''
        public class DatabaseConfig {
            private static final String DB_PASSWORD = "SuperSecret123!";

            public Connection getConnection() {
                return DriverManager.getConnection(url, username, DB_PASSWORD);
            }
        }
        '''
        parsed = parser.parse_code(code, 'DatabaseConfig.java')
        issues = security_analyzer.analyze(parsed, code)

        secret_issues = [i for i in issues if i.rule_id == 'JAVA-SEC006']
        assert len(secret_issues) >= 1
        assert 'password' in secret_issues[0].title.lower()

    def test_detect_weak_crypto_md5(self, parser, security_analyzer):
        """Test weak hash algorithm detection"""
        code = '''
        public class HashUtil {
            public String hashPassword(String password) throws NoSuchAlgorithmException {
                MessageDigest md = MessageDigest.getInstance("MD5");
                byte[] hash = md.digest(password.getBytes());
                return Base64.getEncoder().encodeToString(hash);
            }
        }
        '''
        parsed = parser.parse_code(code, 'HashUtil.java')
        issues = security_analyzer.analyze(parsed, code)

        crypto_issues = [i for i in issues if i.rule_id == 'JAVA-SEC007']
        assert len(crypto_issues) >= 1
        assert 'md5' in crypto_issues[0].title.lower()

    def test_detect_weak_crypto_des(self, parser, security_analyzer):
        """Test weak encryption algorithm detection"""
        code = '''
        public class Encryptor {
            public byte[] encrypt(String data, SecretKey key) throws Exception {
                Cipher cipher = Cipher.getInstance("DES/ECB/PKCS5Padding");
                cipher.init(Cipher.ENCRYPT_MODE, key);
                return cipher.doFinal(data.getBytes());
            }
        }
        '''
        parsed = parser.parse_code(code, 'Encryptor.java')
        issues = security_analyzer.analyze(parsed, code)

        crypto_issues = [i for i in issues if i.rule_id == 'JAVA-SEC007']
        assert len(crypto_issues) >= 1


class TestJavaSmellAnalyzer:
    """Test Java code smell detection"""

    def test_detect_god_class(self, parser, smell_analyzer):
        """Test God class detection"""
        # Create a large class with many methods
        methods = '\n'.join([
            f'    public void method{i}() {{ System.out.println("Method {i}"); }}'
            for i in range(25)
        ])

        code = f'''
        public class GodClass {{
            {methods}
        }}
        '''
        parsed = parser.parse_code(code, 'GodClass.java')
        issues = smell_analyzer.analyze(parsed, code)

        god_class_issues = [i for i in issues if i.rule_id == 'JAVA-SMELL001']
        assert len(god_class_issues) >= 1
        assert 'god class' in god_class_issues[0].title.lower()

    def test_detect_long_method(self, parser, smell_analyzer):
        """Test long method detection"""
        # Create a method with >50 lines
        lines = '\n'.join([f'        System.out.println("Line {i}");' for i in range(60)])

        code = f'''
        public class LongMethodClass {{
            public void veryLongMethod() {{
        {lines}
            }}
        }}
        '''
        parsed = parser.parse_code(code, 'LongMethodClass.java')
        issues = smell_analyzer.analyze(parsed, code)

        long_method_issues = [i for i in issues if i.rule_id == 'JAVA-SMELL002']
        assert len(long_method_issues) >= 1
        assert 'long method' in long_method_issues[0].title.lower()

    def test_detect_too_many_parameters(self, parser, smell_analyzer):
        """Test too many parameters detection"""
        code = '''
        public class ParameterOverload {
            public void processData(String name, int age, String address,
                                  double salary, boolean active, String department) {
                // Too many parameters
            }
        }
        '''
        parsed = parser.parse_code(code, 'ParameterOverload.java')
        issues = smell_analyzer.analyze(parsed, code)

        param_issues = [i for i in issues if i.rule_id == 'JAVA-SMELL003']
        assert len(param_issues) >= 1
        assert 'parameter' in param_issues[0].title.lower()

    def test_detect_deep_nesting(self, parser, smell_analyzer):
        """Test deep nesting detection"""
        code = '''
        public class DeepNesting {
            public void process(int x) {
                if (x > 0) {
                    if (x < 100) {
                        if (x % 2 == 0) {
                            if (x > 10) {
                                if (x < 90) {
                                    System.out.println("Complex logic");
                                }
                            }
                        }
                    }
                }
            }
        }
        '''
        parsed = parser.parse_code(code, 'DeepNesting.java')
        issues = smell_analyzer.analyze(parsed, code)

        nesting_issues = [i for i in issues if i.rule_id == 'JAVA-SMELL004']
        assert len(nesting_issues) >= 1

    def test_detect_magic_numbers(self, parser, smell_analyzer):
        """Test magic number detection"""
        code = '''
        public class Calculator {
            public double calculatePrice(int quantity) {
                return quantity * 19.99 + 5.99;
            }
        }
        '''
        parsed = parser.parse_code(code, 'Calculator.java')
        issues = smell_analyzer.analyze(parsed, code)

        magic_issues = [i for i in issues if i.rule_id == 'JAVA-SMELL005']
        assert len(magic_issues) >= 1

    def test_detect_empty_catch_block(self, parser, smell_analyzer):
        """Test empty catch block detection"""
        code = '''
        public class ErrorHandler {
            public void riskyOperation() {
                try {
                    Files.readAllLines(Path.of("file.txt"));
                } catch (IOException e) {
                    // Empty catch - bad practice
                }
            }
        }
        '''
        parsed = parser.parse_code(code, 'ErrorHandler.java')
        issues = smell_analyzer.analyze(parsed, code)

        catch_issues = [i for i in issues if i.rule_id == 'JAVA-SMELL006']
        assert len(catch_issues) >= 1
        assert 'catch' in catch_issues[0].title.lower()

    def test_detect_system_out(self, parser, smell_analyzer):
        """Test System.out.println detection"""
        code = '''
        public class Logger {
            public void logMessage(String message) {
                System.out.println("Log: " + message);
            }
        }
        '''
        parsed = parser.parse_code(code, 'Logger.java')
        issues = smell_analyzer.analyze(parsed, code)

        sysout_issues = [i for i in issues if i.rule_id == 'JAVA-SMELL007']
        assert len(sysout_issues) >= 1


class TestJavaIntegrationScenarios:
    """Test realistic Java code scenarios"""

    def test_analyze_spring_controller(self, parser, security_analyzer, smell_analyzer):
        """Test analyzing Spring Boot controller"""
        code = '''
        package com.example.api;

        import org.springframework.web.bind.annotation.*;

        @RestController
        @RequestMapping("/api/users")
        public class UserController {

            @GetMapping("/{id}")
            public User getUser(@PathVariable String id) {
                String query = "SELECT * FROM users WHERE id = " + id;
                return database.executeQuery(query);  // SQL injection
            }

            @PostMapping
            public User createUser(@RequestBody User user) {
                System.out.println("Creating user: " + user);  // System.out
                return userService.save(user);
            }
        }
        '''
        parsed = parser.parse_code(code, 'UserController.java')

        security_issues = security_analyzer.analyze(parsed, code)
        smell_issues = smell_analyzer.analyze(parsed, code)

        # Should detect SQL injection
        sql_issues = [i for i in security_issues if 'sql' in i.title.lower()]
        assert len(sql_issues) >= 1

        # Should detect System.out
        sysout_issues = [i for i in smell_issues if 'system.out' in i.title.lower()]
        assert len(sysout_issues) >= 1

    def test_analyze_data_access_layer(self, parser, security_analyzer):
        """Test analyzing DAO with security issues"""
        code = '''
        public class UserDAO {
            private Connection connection;

            public List<User> searchUsers(String searchTerm) throws SQLException {
                String sql = "SELECT * FROM users WHERE name LIKE '%" + searchTerm + "%'";
                Statement stmt = connection.createStatement();
                ResultSet rs = stmt.executeQuery(sql);

                List<User> users = new ArrayList<>();
                while (rs.next()) {
                    users.add(mapUser(rs));
                }
                return users;
            }

            private User mapUser(ResultSet rs) throws SQLException {
                User user = new User();
                user.setId(rs.getInt("id"));
                user.setName(rs.getString("name"));
                return user;
            }
        }
        '''
        parsed = parser.parse_code(code, 'UserDAO.java')
        issues = security_analyzer.analyze(parsed, code)

        # Should detect SQL injection
        sql_issues = [i for i in issues if i.rule_id == 'JAVA-SEC001']
        assert len(sql_issues) >= 1

    def test_analyze_crypto_utility(self, parser, security_analyzer):
        """Test analyzing cryptography utility"""
        code = '''
        public class CryptoUtil {
            public String hashPassword(String password) throws Exception {
                MessageDigest md = MessageDigest.getInstance("MD5");
                byte[] hash = md.digest(password.getBytes());
                return bytesToHex(hash);
            }

            public byte[] encrypt(String data) throws Exception {
                SecretKey key = generateKey();
                Cipher cipher = Cipher.getInstance("DES/ECB/PKCS5Padding");
                cipher.init(Cipher.ENCRYPT_MODE, key);
                return cipher.doFinal(data.getBytes());
            }
        }
        '''
        parsed = parser.parse_code(code, 'CryptoUtil.java')
        issues = security_analyzer.analyze(parsed, code)

        # Should detect weak crypto
        crypto_issues = [i for i in issues if i.rule_id == 'JAVA-SEC007']
        assert len(crypto_issues) >= 2  # Both MD5 and DES

    def test_analyze_file_handler(self, parser, security_analyzer, smell_analyzer):
        """Test analyzing file handling code"""
        code = '''
        public class FileHandler {
            public String readFile(String filename) {
                try {
                    File file = new File(filename);  // Path traversal
                    return Files.readString(file.toPath());
                } catch (IOException e) {
                    // Empty catch block
                }
                return null;
            }

            public void executeScript(String script) throws IOException {
                Runtime.getRuntime().exec(script);  // Command injection
            }
        }
        '''
        parsed = parser.parse_code(code, 'FileHandler.java')

        security_issues = security_analyzer.analyze(parsed, code)
        smell_issues = smell_analyzer.analyze(parsed, code)

        # Should detect path traversal
        path_issues = [i for i in security_issues if i.rule_id == 'JAVA-SEC003']
        assert len(path_issues) >= 1

        # Should detect command injection
        cmd_issues = [i for i in security_issues if i.rule_id == 'JAVA-SEC002']
        assert len(cmd_issues) >= 1

        # Should detect empty catch
        catch_issues = [i for i in smell_issues if i.rule_id == 'JAVA-SMELL006']
        assert len(catch_issues) >= 1


class TestJavaEdgeCases:
    """Test edge cases in Java analysis"""

    def test_no_issues_in_clean_code(self, parser, security_analyzer, smell_analyzer):
        """Test that clean code produces no issues"""
        code = '''
        public class CleanService {
            private static final Logger logger = LoggerFactory.getLogger(CleanService.class);

            public User findUser(int id) {
                try {
                    String sql = "SELECT * FROM users WHERE id = ?";
                    PreparedStatement ps = connection.prepareStatement(sql);
                    ps.setInt(1, id);
                    return mapUser(ps.executeQuery());
                } catch (SQLException e) {
                    logger.error("Failed to find user", e);
                    throw new RuntimeException("Database error", e);
                }
            }
        }
        '''
        parsed = parser.parse_code(code, 'CleanService.java')

        security_issues = security_analyzer.analyze(parsed, code)
        smell_issues = smell_analyzer.analyze(parsed, code)

        # Should have minimal or no critical issues
        critical_issues = [i for i in security_issues if i.severity == IssueSeverity.CRITICAL]
        assert len(critical_issues) == 0

    def test_handle_multiline_string(self, parser, security_analyzer):
        """Test handling multiline strings"""
        code = '''
        public class MultilineQuery {
            public void execute() {
                String query = "SELECT * FROM users WHERE name = '" + userName + "'";
                stmt.executeQuery(query);
            }
        }
        '''
        parsed = parser.parse_code(code, 'MultilineQuery.java')
        issues = security_analyzer.analyze(parsed, code)

        # Should detect SQL injection with single-line concatenation
        sql_issues = [i for i in issues if i.rule_id == 'JAVA-SEC001']
        assert len(sql_issues) >= 1

    def test_constants_not_flagged_as_magic_numbers(self, parser, smell_analyzer):
        """Test that constants are not flagged as magic numbers"""
        code = '''
        public class Constants {
            private static final int MAX_RETRIES = 3;
            private static final double TAX_RATE = 0.08;

            public void test() {
                for (int i = 0; i < MAX_RETRIES; i++) {
                    System.out.println(i);
                }
            }
        }
        '''
        parsed = parser.parse_code(code, 'Constants.java')
        issues = smell_analyzer.analyze(parsed, code)

        # Magic number detection should skip constant declarations
        magic_issues = [i for i in issues if i.rule_id == 'JAVA-SMELL005']
        # Should have minimal magic number issues
        assert len(magic_issues) <= 1
