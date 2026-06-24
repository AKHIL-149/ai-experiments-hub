# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.5.x   | :white_check_mark: |
| < 0.5   | :x:                |

## Reporting a Vulnerability

We take the security of AI Code Review Assistant seriously. If you have discovered a security vulnerability, please report it to us responsibly.

### Reporting Process

1. **DO NOT** open a public GitHub issue for security vulnerabilities
2. Email security reports to: [security contact - replace with actual email]
3. Include the following information:
   - Type of vulnerability
   - Full paths of source file(s) related to the vulnerability
   - Location of the affected source code (tag/branch/commit or direct URL)
   - Step-by-step instructions to reproduce the issue
   - Proof-of-concept or exploit code (if possible)
   - Impact of the vulnerability

### Response Timeline

- **Initial Response**: Within 48 hours
- **Vulnerability Confirmation**: Within 7 days
- **Security Fix**: Within 30 days for critical vulnerabilities
- **Public Disclosure**: After fix is released and users have time to update

### Bug Bounty Program

Currently, we do not offer a paid bug bounty program. However, we will:
- Acknowledge your contribution in our security advisories
- Credit you in our release notes (unless you prefer to remain anonymous)
- Provide early access to security updates

## Security Best Practices

### For Users

#### 1. Secure Configuration

- **Change Default Credentials**: Never use default passwords or tokens
- **Environment Variables**: Store secrets in `.env` file, never commit to version control
- **HTTPS Only**: Always use HTTPS in production environments
- **Session Security**: Set `COOKIE_SECURE=true` in production

```bash
# .env example (production)
COOKIE_SECURE=true
SESSION_TTL_DAYS=7
ALLOWED_ORIGINS=https://yourdomain.com
```

#### 2. GitHub Integration

- **Token Permissions**: Use GitHub tokens with minimal required permissions
- **Webhook Secrets**: Always configure `GITHUB_WEBHOOK_SECRET`
- **GitHub App**: Use GitHub App authentication instead of personal access tokens when possible

```bash
# Minimal token permissions required:
# - repo:status
# - public_repo (for public repos only)
# - read:org (if using organization features)
```

#### 3. Network Security

- **Firewall**: Restrict access to application ports
- **Rate Limiting**: Configure appropriate rate limits
- **CORS**: Whitelist only trusted origins

```bash
# Rate limiting configuration
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000
```

#### 4. Database Security

- **PostgreSQL**: Use PostgreSQL in production, not SQLite
- **Connection Encryption**: Use SSL/TLS for database connections
- **Principle of Least Privilege**: Database user should have minimal permissions

```bash
# Production database configuration
DATABASE_URL=postgresql://reviewer:password@localhost:5432/codereviewer?sslmode=require
```

#### 5. Docker Security

- **Non-Root User**: Application runs as non-root user (appuser)
- **Read-Only Filesystem**: Mount volumes as read-only where possible
- **Network Isolation**: Use Docker networks for service isolation
- **Image Scanning**: Scan Docker images for vulnerabilities

```bash
# Run security scan
docker scan code-review-assistant:latest
```

### For Developers

#### 1. Code Security

- **No Hardcoded Secrets**: Use environment variables for all secrets
- **SQL Injection Prevention**: Always use parameterized queries
- **XSS Prevention**: Sanitize all user inputs, escape outputs
- **CSRF Protection**: Validate CSRF tokens on state-changing operations

```python
# Good - Parameterized query
session.query(User).filter(User.username == username).first()

# Bad - String interpolation
session.execute(f"SELECT * FROM users WHERE username = '{username}'")
```

#### 2. Authentication Security

- **Password Hashing**: Use bcrypt with appropriate work factor
- **Session Management**: Secure session storage with expiration
- **RBAC**: Implement role-based access control

```python
# Password hashing
import bcrypt
hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))
```

#### 3. Input Validation

- **Pydantic Models**: Use Pydantic for request validation
- **File Upload Limits**: Enforce file size and type restrictions
- **Path Traversal Prevention**: Validate and sanitize file paths

```python
# Input validation with Pydantic
from pydantic import BaseModel, validator

class UserRegistration(BaseModel):
    username: str
    email: EmailStr
    password: str

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v
```

#### 4. Dependencies

- **Keep Updated**: Regularly update dependencies
- **Vulnerability Scanning**: Use `pip-audit` or `safety` to scan dependencies
- **Pin Versions**: Pin exact versions in `requirements.txt`

```bash
# Scan dependencies for vulnerabilities
pip-audit
# or
safety check
```

#### 5. Logging Security

- **No Sensitive Data**: Never log passwords, tokens, or API keys
- **Structured Logging**: Use structured logging with sensitive data masking
- **Log Retention**: Implement appropriate log retention policies

```python
# Mask sensitive data in logs
from src.middleware.logging_middleware import structured_logger

structured_logger.info("User login", username=username)  # OK
structured_logger.info("User login", password=password)  # BAD - password will be masked
```

## Known Security Considerations

### 1. GitHub Token Security

- GitHub personal access tokens have full access to repositories
- Store tokens securely in environment variables
- Rotate tokens regularly
- Consider using GitHub Apps for better security

### 2. Analysis of Untrusted Code

- This tool analyzes code from repositories, which may contain malicious code
- Code analysis runs in isolated environment
- Never execute untrusted code during analysis
- Parser vulnerabilities could be exploited by malicious code

### 3. Redis Security

- Redis used for caching and Celery may contain sensitive data
- Configure Redis authentication in production
- Use Redis ACLs to restrict access
- Enable SSL/TLS for Redis connections

### 4. Celery Worker Security

- Workers execute analysis tasks asynchronously
- Ensure workers run with minimal privileges
- Isolate worker environment from sensitive systems
- Monitor worker resource usage

## Security Features

### Implemented Security Controls

- ✅ Password hashing with bcrypt
- ✅ Session-based authentication with expiration
- ✅ Rate limiting on API endpoints
- ✅ CORS protection with origin validation
- ✅ SQL injection prevention via ORM
- ✅ XSS prevention via template escaping
- ✅ Security headers (X-Frame-Options, CSP, etc.)
- ✅ Input validation with Pydantic
- ✅ Sensitive data masking in logs
- ✅ GitHub webhook signature verification
- ✅ Docker security (non-root user, minimal image)
- ✅ File upload restrictions
- ✅ RBAC (Role-Based Access Control)

### Security Roadmap

- ⬜ Two-factor authentication (2FA)
- ⬜ OAuth2 integration
- ⬜ Audit logging
- ⬜ Automated dependency scanning in CI/CD
- ⬜ Security.txt file
- ⬜ SAST (Static Application Security Testing) integration
- ⬜ Penetration testing

## Security Checklist for Deployment

### Pre-Deployment

- [ ] All secrets stored in environment variables
- [ ] `.env` file added to `.gitignore`
- [ ] `COOKIE_SECURE=true` in production
- [ ] Strong `GITHUB_WEBHOOK_SECRET` configured
- [ ] Database uses PostgreSQL with SSL
- [ ] Redis authentication enabled
- [ ] Rate limits configured appropriately
- [ ] CORS origins whitelisted
- [ ] Security headers enabled
- [ ] Docker image scanned for vulnerabilities

### Post-Deployment

- [ ] HTTPS enabled with valid SSL certificate
- [ ] Security headers verified (use securityheaders.com)
- [ ] Dependency vulnerability scan passed
- [ ] Logs are being collected and monitored
- [ ] Backups configured and tested
- [ ] Incident response plan documented
- [ ] Security contact information published

## Incident Response

### In Case of Security Incident

1. **Assess Impact**: Determine scope and severity
2. **Contain**: Isolate affected systems
3. **Notify**: Inform affected users within 72 hours
4. **Remediate**: Apply fixes and patches
5. **Document**: Create incident report
6. **Review**: Update security measures to prevent recurrence

## Security Resources

### Tools

- **OWASP ZAP**: Web application security scanner
- **pip-audit**: Python dependency vulnerability scanner
- **safety**: Python package security checker
- **bandit**: Python security linter
- **Docker Bench**: Docker security auditing

### References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [FastAPI Security Best Practices](https://fastapi.tiangolo.com/tutorial/security/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)

## Contact

For security-related questions or concerns:
- Security Email: [security contact]
- General Issues: [GitHub Issues](https://github.com/user/repo/issues) (non-security)

## Acknowledgments

We thank the following security researchers for responsible disclosure:
- [List will be maintained here]

---

**Last Updated**: 2026-06-24
**Version**: 0.5.28
