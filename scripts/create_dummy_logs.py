import os
import datetime
from pathlib import Path

def create_dummy_logs():
    # Base path for logs - simulating /var/log in a temp dir or local dir for testing
    # Since we are on Windows/Agent env, let's create them inside the project for safety 
    # and update config to point there for the test, OR we just mirror the structure locally.
    
    # We will create 'var_log' in project root
    base_dir = Path("var_log")
    
    today = datetime.datetime.now()
    yyyy = today.strftime("%Y")
    mm = today.strftime("%m")
    dd = today.strftime("%d")
    
    # 1. AWS ECS JSON Logs
    # Pattern: /var/log/syslog/{YYYY}/{MM}/{DD}/application_logs/web-server/{guid}-{date}.log
    ecs_dir = base_dir / "syslog" / yyyy / mm / dd / "application_logs" / "web-server"
    ecs_dir.mkdir(parents=True, exist_ok=True)
    
    with open(ecs_dir / f"guid123-{today.strftime('%Y-%m-%d')}.log", "w") as f:
        f.write('{"timestamp": "2023-10-27T10:00:00Z", "level": "INFO", "message": "User login success", "user_id": 42}\n')
        f.write('{"timestamp": "2023-10-27T10:01:00Z", "level": "ERROR", "message": "Database connection failed", "retry": 1}\n')

    # 2. Pylons Syslog
    # Pattern: /var/log/ecs/{YYYY}/{MM}/{DD}/web-server.log
    pylons_dir = base_dir / "ecs" / yyyy / mm / dd
    pylons_dir.mkdir(parents=True, exist_ok=True)
    
    with open(pylons_dir / "web-server.log", "w") as f:
        f.write('Oct 27 10:00:00 server1 web-server[1234]: INFO Starting application...\n')
        f.write('Oct 27 10:05:00 server1 web-server[1234]: WARN High memory usage detected\n')
        f.write('Oct 27 10:06:00 server1 web-server[1234]: ERROR OOM Exception in worker process\n')

    # 3. AWS SES JSON Logs
    # Pattern: /var/log/ses/{YYYY}/{MM}/{DD}/SES/{guid}-{date}.log
    ses_dir = base_dir / "ses" / yyyy / mm / dd / "SES"
    ses_dir.mkdir(parents=True, exist_ok=True)
    
    with open(ses_dir / f"ses-id-999-{today.strftime('%Y-%m-%d')}.log", "w") as f:
        f.write('{"mail_id": "m123", "status": "sent", "recipient": "user@example.com"}\n')

    print(f"Created dummy logs in {base_dir.absolute()}")
    return base_dir.absolute()

if __name__ == "__main__":
    create_dummy_logs()
