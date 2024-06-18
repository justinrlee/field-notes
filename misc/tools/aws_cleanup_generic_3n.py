#!/usr/bin/python3
# BY DEFAULT, WILL ONLY RUN AGAINST TEST INSTANCES
# MUST USE --full FLAG TO RUN AGAINST WHOLE ACCOUNT

# On fresh Ubuntu instance, install prereqs:
# sudo apt-get update; sudo apt-get install -y python3-pip;
# python3 -m pip install boto3
import boto3
import datetime
import enum
import argparse

# Run only against instances in a specific region, for testing
test_region_override = ['us-east-1', 'us-east-2']

# Run only against instances matching specific tags
test_filter = [
    {
        'Name': 'tag:justin',
        'Values': ['test']
    },
]

NOTIFICATION_PERIOD_1 = 15
NOTIFICATION_PERIOD_2 = 7
NOTIFICATION_PERIOD_3 = 2

MAX_STOP_DAYS = 62
DEFAULT_STOP_DAYS = 31
MAX_TERMINATE_DAYS = 62
DEFAULT_TERMINATE_DAYS = 31

DEFAULT_SEARCH_FILTER = []

# D_MAX = datetime.date.min
D_TODAY = datetime.date.today()

# Tag names
T_OWNER_EMAIL = "owner_email"
T_EMAIL = "email"
T_DIVVY_OWNER = "divvy_owner"
T_DIVVY_LAST_MODIFIED_BY = "divvy_last_modified_by"
T_AUTOSCALING_GROUP = "aws:autoscaling:groupName"
T_NAME = "Name"
# T_NOTIFICATION_DATE = "cleanup_notification_date"
T_EXCEPTION = "aws_cleaner/cleanup_exception"
T_STOP_DATE = "aws_cleaner/stop_date"
T_TERMINATE_DATE = "aws_cleaner/terminate_date"
T_NOTIFICATION_1 = "aws_cleaner/notifications/1"
T_NOTIFICATION_2 = "aws_cleaner/notifications/2"
T_NOTIFICATION_3 = "aws_cleaner/notifications/3"

def ec2_update_tag(instance_id, instance_name, region, key, value):
    # TODO: In the future, could batch this up, for now doing it one at a time
    if dry_run:
        print("DRY RUN: Skipping update of tag on {0} [{1}] in region {2}: setting {3} to {4}".format(
            instance_name,
            instance_id,
            region,
            key,
            value))
    else:
        print("Updating tag on {0} [{1}] in region {2}: setting {3} to {4}".format(
            instance_name,
            instance_id,
            region,
            key,
            value))
        # This is super sloppy; right now we're relying on the fact that this is called after ec2_client has created for the relevant region
        # Later could either pass it in, or create an array of clients for regions
        # str(value) takes care of converting datetime.date to string in isoformat '2024-01-01'
        ec2_client.create_tags(
            Resources = [instance_id],
            Tags = [{'Key': key, 'Value': str(value)}]
        )

def ec2_stop(instance_id, instance_name, region):
    if dry_run or tag_only:
        print("DRY RUN: Stopping instance {0} [{1}] in region {2}".format(instance_name, instance_id, region))
    else:
        print("Stopping instance {0} [{1}] in region {2}".format(instance_name, instance_id, region))
        ec2_client.stop_instances(InstanceIds=[instance_id])

def ec2_terminate(instance_id, instance_name, region):
    if dry_run or tag_only:
        print("DRY RUN: Terminating instance {0} [{1}] in region {2}".format(instance_name, instance_id, region))
    else:
        print("Terminating instance {0} [{1}] in region {2}".format(instance_name, instance_id, region))
        ec2_client.terminate_instances(InstanceIds=[instance_id])

# Takes the following:
    # idn_action_date: Currently set action date
    # idn_notification_1: Current dn_notification_1
    # idn_notification_2: Current dn_notification_2
    # idn_notification_3: Current dn_notification_3
    # i_default_days: Default number of days
    # i_max_days: Max number of days
# Returns dict with the following:
    # odn_notification_1: New dn_notification_1
    # odn_notification_2: New dn_notification_2
    # odn_notification_3: New dn_notification_3
    # odn_action_date
    # result ENUM
# All actual changes (tags and/or instance modification) occurs in calling code, not here.

def determine_action(
        idn_action_date,
        idn_notification_1,
        idn_notification_2,
        idn_notification_3,
        i_default_days,
        i_max_days
    ):
    if idn_action_date is None:
        message = "Set unset date"
        return {
            'odn_notification_1': None,
            'odn_notification_2': None,
            'odn_notification_3': None,
            'odn_action_date': d_run_date + datetime.timedelta(days = i_default_days),
            'result': Result.ADD_ACTION_DATE
        }

    elif idn_action_date - d_run_date > i_max_days:
        message = "Set to max"
        return {
            'odn_notification_1': None,
            'odn_notification_2': None,
            'odn_notification_3': None,
            'odn_action_date': d_run_date + datetime.timedelta(days = i_max_days),
            'result': Result.RESET_ACTION_DATE
        }

    elif idn_action_date < d_run_date:
        if idn_notification_1 is None or idn_notification_2 is None or idn_notification_3 is None:
            # TODO FIX THIS LOGIC; for now this tries to resend all three notifications
            message = "Extend stop date (missing notifications)"
            return {
                'odn_notification_1': None,
                'odn_notification_2': None,
                'odn_notification_3': None,
                'odn_action_date': d_run_date + datetime.timedelta(days = 3),
                'result': Result.PAST_BUMP_ACTION_DATE
            }

        else:
            message = "Complete action"
            return {
                'odn_notification_1': None,
                'odn_notification_2': None,
                'odn_notification_3': None,
                'odn_action_date': d_run_date,
                'result': Result.COMPLETE_ACTION
            }
    
    else:
        remaining_days = idn_action_date - d_run_date

        if dn_notification_1 is None and remaining_days < NOTIFICATION_PERIOD_1:
            message = "Send first notification"
            return {
                'odn_notification_1': d_run_date,
                'odn_notification_2': None,
                'odn_notification_3': None,
                'odn_action_date': idn_action_date,
                'result': Result.SEND_NOTIFICATION_1
            }

        elif dn_notification_2 and remaining_days < NOTIFICATION_PERIOD_2:
            message = "Send second notification"
            return {
                'odn_notification_1': dn_notification_1,
                'odn_notification_2': d_run_date,
                'odn_notification_3': None,
                'odn_action_date': idn_action_date,
                'result': Result.SEND_NOTIFICATION_2
            }
        
        elif dn_notification_3 and remaining_days < NOTIFICATION_PERIOD_3:
            message = "Send third notification"
            return {
                'odn_notification_1': dn_notification_1,
                'odn_notification_2': dn_notification_2,
                'odn_notification_3': d_run_date,
                'odn_action_date': idn_action_date,
                'result': Result.SEND_NOTIFICATION_3
            }

        else:
            message = "Log without notification"
            return {
                'odn_notification_1': dn_notification_1,
                'odn_notification_2': dn_notification_2,
                'odn_notification_3': dn_notification_3,
                'odn_action_date': idn_action_date,
                'result': Result.LOG_NO_NOTIFICATION
            }        

class Result(str, enum.Enum):
    ADD_ACTION_DATE             = "add_action_date"
    RESET_ACTION_DATE           = "reset_action_date"
    COMPLETE_ACTION             = "complete_action"
    PAST_BUMP_ACTION_DATE       = "past_bump_action_date"

    SEND_NOTIFICATION_1         = "send_notification_1"
    SEND_NOTIFICATION_2         = "send_notification_2"
    SEND_NOTIFICATION_3         = "send_notification_3"
    LOG_NO_NOTIFICATION         = "log_no_notification"

    IGNORE_OTHER_STATES         = "ignore_other_states"
    SKIP_EXCEPTION              = "skip_exception"
    # PAST_EXPIRED_NOTIFICATION   = "past_expired_notification"
    # FUTURE_NORMAL_NOTIFY        = "future_normal_notify"
    # WINDOW_EXPIRED_BUMP         = "window_expired_bump"
    # WINDOW_NORMAL_NOTIFY        = "window_normal_notify"
    # WINDOW_RECENT_BUMP          = "window_recent_bump"
    # OVERRIDE_ACTION_DATE        = "override_action_date"
    # EXCEPTION                   = "exception"

notify_messages = {
    Result.ADD_ACTION_DATE             : "ADD_ACTION_DATE: Added {action} date (tag [{tag}]) of {date} to {instance_type} {instance_name} [{instance_id}] in region {region}",
    Result.RESET_ACTION_DATE           : "RESET_ACTION_DATE: Updated tag [{tag}] (date too far out): {instance_type} {instance_name} [{instance_id}] in region {region}: {action} date set to {date}",
    Result.COMPLETE_ACTION             : "COMPLETE_ACTION: Completed {action} {instance_type} {instance_name} [{instance_id}] in region {region} (tag [{tag}])",
    Result.PAST_BUMP_ACTION_DATE       : "PAST_BUMP_ACTION_DATE: Updated tag [{tag}]: will {action} {instance_type} {instance_name} [{instance_id}] in region {region} on or after {date}",
    
    Result.SEND_NOTIFICATION_1       : "SEND_NOTIFICATION_1: LOREM IPSUM",
    Result.SEND_NOTIFICATION_2       : "SEND_NOTIFICATION_2: LOREM IPSUM",
    Result.SEND_NOTIFICATION_3       : "SEND_NOTIFICATION_3: LOREM IPSUM",
    Result.LOG_NO_NOTIFICATION       : "LOG_NO_NOTIFICATION: LOREM IPSUM",

    Result.IGNORE_OTHER_STATES       : "IGNORE_OTHER_STATES: LOREM IPSUM",
    Result.SKIP_EXCEPTION            : "SKIP_EXCEPTION: LOREM IPSUM",

    # Result.PAST_EXPIRED_NOTIFICATION   : "PAST_EXPIRED_NOTIFICATION: Updated tag [{tag}]: Will {action} {instance_type} {instance_name} [{instance_id}] in region {region} on or after {date}",
    # Result.FUTURE_NORMAL_NOTIFY        : "FUTURE_NORMAL_NOTIFY:  Will {action} {instance_type} {instance_name} [{instance_id}] in region {region} on or after {date} (tag [{tag}])",
    # Result.WINDOW_EXPIRED_BUMP         : "WINDOW_EXPIRED_BUMP:  Updated tag [{tag}]: will {action} {instance_type} {instance_name} [{instance_id}] in region {region} on or after {date}",
    # Result.WINDOW_NORMAL_NOTIFY        : "WINDOW_NORMAL_NOTIFY:  Will {action} {instance_type} {instance_name} [{instance_id}] in region {region} on or after {date} (tag [{tag}])",
    # Result.WINDOW_RECENT_BUMP          : "WINDOW_RECENT_BUMP:  Updated tag [{tag}]: will {action} {instance_type} {instance_name} [{instance_id}] in region {region} on or after {date}",
    # Result.OVERRIDE_ACTION_DATE        : "OVERRIDE_ACTION_DATE: Updated {action} date (tag [{tag}]) of {date} to {instance_type} {instance_name} [{instance_id}] in region {region}",
    # Result.EXCEPTION                   : "EXCEPTION: {instance_type} {instance_name} [{instance_id}] in region {region} has an exception",
}

detailed_log = []

def add_to_log(
        email,
        instance_type,
        instance_name,
        instance_id,
        region,
        action,
        tag,
        result,
        old_date,
        new_date,
        message,
        ):
    detailed_log.append({
        'email' : email,
        'instance_type' : instance_type,
        'instance_name' : instance_name,
        'instance_id' : instance_id,
        'region' : region,
        'action' : action,
        'tag' : tag,
        'result' : result,
        'old_date': old_date,
        'new_date' : new_date,
        'message': message,
    })


# Get value of key from dictionary (or return None)
def value_or_none(tags, tag):
    return tags[tag] if tag in tags else None

# Same as above, but convert to a datetime.date on the way (and return None)
def date_or_none(tags, tag):
    try:
        return datetime.date.fromisoformat(tags[tag])
    except:
        return None

############################

# Parse Arguments
parser = argparse.ArgumentParser(description="AWS Cleanup Script")
parser.add_argument('--rundate')
parser.add_argument('--dry-run', action='store_true')
parser.add_argument('--tag-only', action='store_true')
parser.add_argument('--full', action='store_true')
parser.add_argument('--override-stop-date', action='store_true')

args = parser.parse_args()

d_run_date = D_TODAY
if args.rundate:
    d_run_date = datetime.date.fromisoformat(args.rundate)

search_filter = DEFAULT_SEARCH_FILTER if args.full else test_filter

use_test_region_filter = not args.full
dry_run = args.dry_run
tag_only = args.tag_only

override_stop_date = args.override_stop_date


# Main process run
print("Running cleaner on {}".format(d_run_date))

if use_test_region_filter:
    regions = test_region_override
    print("Using test regions")
else:
    ec2 = boto3.client('ec2', region_name='us-east-1')
    print("Getting regions")
    regions = [region['RegionName'] for region in ec2.describe_regions()['Regions']]

print("Using regions: {}".format(regions))

for region in regions:
    print("\nProcessing region {0}".format(region))
    ec2_client = boto3.client('ec2', region_name = region)

    # https://stackoverflow.com/a/952952
    # instances = [reservation["Instances"] for reservation in ec2_client.describe_instances(Filters=justin_filter)["Reservations"]]
    # TODO: Add pagination, maybe (hopefully we don't have more than 500 instance running...)
    ec2_instances = [instance for reservation in ec2_client.describe_instances(MaxResults=500,Filters=search_filter)["Reservations"] for instance in reservation["Instances"]]

    # https://confluentinc.atlassian.net/wiki/spaces/~457145999/pages/3318745562/Cloud+Spend+Reduction+Proposal+AWS+Solutions+Engineering+Account
    for instance in ec2_instances:
        print("")
        instance_id = instance["InstanceId"]
        state = instance["State"]["Name"]

        print("Processing {1} instance {0} in region {2}".format(instance_id, state, region))
        
        if "Tags" not in instance:
            tags = {}
        else:
            tags = {tag["Key"]:tag["Value"] for tag in instance["Tags"]}

        autoscaling_group = value_or_none(T_AUTOSCALING_GROUP)
        exception = value_or_none(T_EXCEPTION)

        # 'dn_' means 'either a Datetime.date or None'
        dn_stop_date = date_or_none(tags, T_STOP_DATE)
        dn_terminate_date = date_or_none(tags, T_TERMINATE_DATE)
        dn_notification_1 = date_or_none(tags, T_NOTIFICATION_1)
        dn_notification_2 = date_or_none(tags, T_NOTIFICATION_2)
        dn_notification_3 = date_or_none(tags, T_NOTIFICATION_3)

        instance_name = value_or_none(T_NAME)
        
        # Rough equivalent to coalesce
        owner_email = value_or_none(T_OWNER_EMAIL) \
            or value_or_none(T_EMAIL) \
            or value_or_none(T_DIVVY_OWNER) \
            or value_or_none(T_DIVVY_LAST_MODIFIED_BY)
        
        print("{} is {}".format(instance_name, state))

        if autoscaling_group is None:
            if exception is None:
                if state == "running":
                    if True:
                        # Returns dict with the following:
                            # odn_notification_1: New dn_notification_1
                            # odn_notification_2: New dn_notification_2
                            # odn_notification_3: New dn_notification_3
                            # odn_action_date
                            # result ENUM

                        r = determine_action(
                            idn_action_date=dn_stop_date,
                            idn_notification_1=dn_notification_1,
                            idn_notification_2=dn_notification_2,
                            idn_notification_3=dn_notification_3,
                            i_default_days=DEFAULT_STOP_DAYS,
                            i_max_days=MAX_STOP_DAYS,
                        )

                        # Update all tags that have changed
                        for tag in [
                            (T_STOP_DATE, dn_stop_date, r['odn_action_date'])
                            (T_NOTIFICATION_1, dn_notification_1, r['odn_notification_1'])
                            (T_NOTIFICATION_2, dn_notification_2, r['odn_notification_2'])
                            (T_NOTIFICATION_3, dn_notification_3, r['odn_notification_3'])
                        ]:
                            if tag[1] != tag[2]:
                                ec2_update_tag(
                                    instance_id=instance_id,
                                    instance_name=instance_name,
                                    region=region,
                                    key=tag[0],
                                    value=tag[2],
                                )

                        message = notify_messages[r['result']].format(
                                instance_type = "EC2",
                                instance_name = instance_name,
                                instance_id = instance_id,
                                region = region,
                                action = "STOP",
                                tag = T_STOP_DATE,
                                date = r['odn_action_date'],
                            )
                        
                        add_to_log(
                            email = owner_email,
                            instance_type = "EC2",
                            instance_name = instance_name,
                            instance_id = instance_id,
                            region = region,
                            action = "STOP",
                            tag = T_STOP_DATE,
                            result = r['result'],
                            old_date = dn_stop_date,
                            new_date = r['odn_action_date'],
                            message = message,
                        )

                        if r['result'] == Result.COMPLETE_ACTION:
                            # On complete, stop the instance
                            # New tags already set, aside from termination date tag
                            ec2_stop(instance_id=instance_id,
                                     instance_name=instance_name,
                                     region=region,
                                     )

                            ec2_update_tag(
                                instance_id=instance_id,
                                instance_name=instance_name,
                                region=region,
                                key=T_TERMINATE_DATE,
                                value=d_run_date + datetime.timedelta(days = DEFAULT_TERMINATE_DAYS),
                            )

                            # TODO: Add log for this?
                    else:
                        pass # Placeholder for 'override' behavior

                elif state == "stopped":
                    if True:
                        # Returns dict with the following:
                            # odn_notification_1: New dn_notification_1
                            # odn_notification_2: New dn_notification_2
                            # odn_notification_3: New dn_notification_3
                            # odn_action_date
                            # result ENUM

                        r = determine_action(
                            idn_action_date=dn_terminate_date,
                            idn_notification_1=dn_notification_1,
                            idn_notification_2=dn_notification_2,
                            idn_notification_3=dn_notification_3,
                            i_default_days=DEFAULT_TERMINATE_DAYS,
                            i_max_days=MAX_TERMINATE_DAYS,
                        )

                        # Update all tags that have changed
                        for tag in [
                            (T_TERMINATE_DATE, dn_terminate_date, r['odn_action_date'])
                            (T_NOTIFICATION_1, dn_notification_1, r['odn_notification_1'])
                            (T_NOTIFICATION_2, dn_notification_2, r['odn_notification_2'])
                            (T_NOTIFICATION_3, dn_notification_3, r['odn_notification_3'])
                        ]:
                            if tag[1] != tag[2]:
                                ec2_update_tag(
                                    instance_id=instance_id,
                                    instance_name=instance_name,
                                    region=region,
                                    key=tag[0],
                                    value=tag[2],
                                )

                        message = notify_messages[r['result']].format(
                                instance_type = "EC2",
                                instance_name = instance_name,
                                instance_id = instance_id,
                                region = region,
                                action = "TERMINATE",
                                tag = T_STOP_DATE,
                                date = r['odn_action_date'],
                            )
                            
                        add_to_log(
                            email = owner_email,
                            instance_type = "EC2",
                            instance_name = instance_name,
                            instance_id = instance_id,
                            region = region,
                            action = "TERMINATE",
                            tag = T_TERMINATE_DATE,
                            result = r['result'],
                            old_date = dn_terminate_date,
                            new_date = r['odn_action_date'],
                            message = message,
                        )

                        if r['result'] == Result.COMPLETE_ACTION:
                            # On complete, terminate the instance
                            ec2_terminate(instance_id=instance_id,
                                     instance_name=instance_name,
                                     region=region,
                                     )

                            # TODO: Add additional log for this?
                    else:
                        pass # Placeholder for 'override' behavior

                else: # State is not running or stopped
                    message = notify_messages[Result.IGNORE_OTHER_STATE].format(
                            instance_type = "EC2",
                            instance_name = instance_name,
                            instance_id = instance_id,
                            region = region,
                            action = "IGNORE",
                            tag = state, # This is a hack
                            date = d_run_date,
                        )
                        
                    add_to_log(
                        email = owner_email,
                        instance_type = "EC2",
                        instance_name = instance_name,
                        instance_id = instance_id,
                        region = region,
                        action = "IGNORE",
                        tag = state, # again, this is a hack
                        result = Result.IGNORE_OTHER_STATES,
                        old_date = d_run_date,
                        new_date = d_run_date,
                        message = message,
                    )

            else: # Exception exists, add to notify list
                message = notify_messages[Result.SKIP_EXCEPTION].format(
                        instance_type = "EC2",
                        instance_name = instance_name,
                        instance_id = instance_id,
                        region = region,
                        action = "SKIP_EXCEPTION",
                        tag = exception, # This is a hack
                        date = d_run_date,
                    )
                    
                add_to_log(
                    email = owner_email,
                    instance_type = "EC2",
                    instance_name = instance_name,
                    instance_id = instance_id,
                    region = region,
                    action = "SKIP_EXCEPTION",
                    tag = exception, # again, this is a hack
                    result = Result.SKIP_EXCEPTION,
                    old_date = d_run_date,
                    new_date = d_run_date,
                    message = message,
                )

        else: # In autoscaling group
            print("Instance {0} is in ASG {1}, skipping".format(instance_id,autoscaling_group))

print("")
print("Today is {}".format(d_run_date))
print("Notification List:")

for item in detailed_log:
    print(item)
