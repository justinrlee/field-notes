#!/usr/bin/python3
# BY DEFAULT, WILL ONLY RUN AGAINST TEST INSTANCES
# MUST USE --full FLAG TO RUN AGAINST WHOLE ACCOUNT

# On fresh Ubuntu instance, install prereqs:
# sudo apt-get install -y python3-pip
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

NOTIFICATION_PERIOD = 7
STOP_ACTION_DAYS = 31
TERMINATE_ACTION_DAYS = 31

DEFAULT_SEARCH_FILTER = []

D_MAX = datetime.date.min
D_TODAY = datetime.date.today()

# Tag names
T_OWNER_EMAIL = "owner_email"
T_EMAIL = "email"
T_DIVVY_OWNER = "divvy_owner"
T_DIVVY_LAST_MODIFIED_BY = "divvy_last_modified_by"
T_EXCEPTION = "cleanup_exception"
T_STOP_DATE = "stop_date"
T_TERMINATE_DATE = "terminate_date"
T_AUTOSCALING_GROUP = "aws:autoscaling:groupName"
T_NOTIFICATION_DATE = "cleanup_notification_date"
T_NAME = "Name"

def ec2_update_tag(instance_id, instance_name, region, key, value):
    # TODO: In the future, could batch this up, for now doing it one at a time
    if dry_run:
        print("DRY RUN: Updating tag on {0} [{1}] in region {2}: setting {3} to {4}".format(
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

class Result(str, enum.Enum):
    PAST_COMPLETE_ACTION        = "past_complete_action"
    PAST_EXPIRED_NOTIFICATION   = "past_expired_notification"
    PAST_BUMP_ACTION_DATE       = "past_bump_action_date"
    ACTION_DATE_TOO_FAR         = "action_date_too_far"
    FUTURE_NORMAL_NOTIFY        = "future_normal_notify"
    WINDOW_EXPIRED_BUMP         = "window_expired_bump"
    WINDOW_NORMAL_NOTIFY        = "window_normal_notify"
    WINDOW_RECENT_BUMP          = "window_recent_bump"
    ADD_ACTION_DATE             = "add_action_date"
    OVERRIDE_ACTION_DATE        = "override_action_date"

notify_messages = {
    Result.PAST_COMPLETE_ACTION        : "PAST_COMPLETE_ACTION: Completed {action} {type} {name} [{instance_id}] in region {region} (tag [{tag}])",
    Result.PAST_EXPIRED_NOTIFICATION   : "PAST_EXPIRED_NOTIFICATION: Updated tag [{tag}]: Will {action} {type} {name} [{instance_id}] in region {region} on or after {date}",
    Result.PAST_BUMP_ACTION_DATE       : "PAST_BUMP_ACTION_DATE: Updated tag [{tag}]: will {action} {type} {name} [{instance_id}] in region {region} on or after {date}",
    Result.ACTION_DATE_TOO_FAR         : "ACTION_DATE_TOO_FAR: Updated tag [{tag}] (date too far out): {type} {name} [{instance_id}] in region {region}: {action} date set to {date}",
    Result.FUTURE_NORMAL_NOTIFY        : "FUTURE_NORMAL_NOTIFY:  Will {action} {type} {name} [{instance_id}] in region {region} on or after {date} (tag [{tag}])",
    Result.WINDOW_EXPIRED_BUMP         : "WINDOW_EXPIRED_BUMP:  Updated tag [{tag}]: will {action} {type} {name} [{instance_id}] in region {region} on or after {date}",
    Result.WINDOW_NORMAL_NOTIFY        : "WINDOW_NORMAL_NOTIFY:  Will {action} {type} {name} [{instance_id}] in region {region} on or after {date} (tag [{tag}])",
    Result.WINDOW_RECENT_BUMP          : "WINDOW_RECENT_BUMP:  Updated tag [{tag}]: will {action} {type} {name} [{instance_id}] in region {region} on or after {date}",
    Result.ADD_ACTION_DATE             : "ADD_ACTION_DATE: Added {action} date (tag [{tag}]) of {date} to {type} {name} [{instance_id}] in region {region}",
    Result.OVERRIDE_ACTION_DATE        : "OVERRIDE_ACTION_DATE: Updated {action} date (tag [{tag}]) of {date} to {type} {name} [{instance_id}] in region {region}",
}

# There's some super janky logic in here because of the notification goals
# Requirements:
# 1) Must have a 'valid' notification at least 7 days before stop
# 2) Most recent notification must be at most 14 days before stop
# 3) We are only storing one notification date (logic might be simpler with notification history, not sure)
# 4) Always notify; don't always update notification date, because:
#     a) If notification is coming up soon, we only know about the most recent notification, not the previous notifications
#     b) Sample scenario:
#         Stopping in in 5 days
#         Notified 3 days ago (This is a valid notification: between 7 and 14 days before delete)
#         If we update the notification date today, we no longer know that the old notification was 5 days ago, and the known gap is now only 3 days, which is invalid

# Takes the following:
    # di_notification_date: Most recent notification (datetime.date)
    # di_action_date: Current action date (datetime.date)
    # i_notification_days: Notification period (integer, in days) (2x is max)
    # i_action_days: Default action time (integer, in days) (2x is max)
# Returns dict with the following:
    # dn_notification_date: New notification date (datetime.date)
    # dn_action_date: New action date (datetime.date)
    # result: result type (Enum)
def determine_action(di_notification_date, di_action_date, i_notification_days, i_action_days):
    print("Current notification date [{}]. Current action date [{}]".format(di_notification_date, di_action_date))
    if di_action_date == D_MAX:
        return {
            'dn_notification_date': d_run_date,
            'dn_action_date': d_run_date + datetime.timedelta(days = i_action_days),
            # complete_action: False,
            'result': Result.ADD_ACTION_DATE,
        }
    if di_action_date <= d_run_date: # Action date has passed
        if d_run_date - di_notification_date > datetime.timedelta(days = 2 * i_notification_days):
            # Last notification too long ago
            return {
                'dn_notification_date': d_run_date,
                'dn_action_date': d_run_date + datetime.timedelta(days = i_notification_days),
                # complete_action: False,
                'result': Result.PAST_EXPIRED_NOTIFICATION,
            }
        elif d_run_date - di_notification_date >= datetime.timedelta(days = i_notification_days):
            # Last notification valid to perform action
            return {
                'dn_notification_date': d_run_date,
                'dn_action_date': d_run_date,
                # complete_action: True,
                'result': Result.PAST_COMPLETE_ACTION,
            }
        else:
            # Last notification too recent
            return {
                'dn_notification_date': di_notification_date,
                'dn_action_date': di_notification_date + datetime.timedelta(days = i_notification_days),
                # complete_action: False,
                'result': Result.PAST_BUMP_ACTION_DATE,
            }
    elif di_action_date - d_run_date > datetime.timedelta(days = 2 * i_action_days): # Action date too far in the future
        return {
            'dn_notification_date': d_run_date,
            'dn_action_date': d_run_date + datetime.timedelta(days = 2 * i_action_days),
            # complete_action: False,
            'result': Result.ACTION_DATE_TOO_FAR,
        }
    else: # Action date in the future
        if di_action_date - d_run_date > datetime.timedelta(days = i_notification_days):
            # Time till action is more than notification days
            return {
                'dn_notification_date': d_run_date,
                'dn_action_date': di_action_date,
                # complete_action: False,
                'result': Result.FUTURE_NORMAL_NOTIFY,
            }
        else:
            # Time till action is less than notification days; compare action date and recent notification date
            if di_action_date - di_notification_date > datetime.timedelta(days = 2 * i_notification_days):
                # Most recent notification too long ago; new notification + bump
                return {
                    'dn_notification_date': d_run_date,
                    'dn_action_date': d_run_date + datetime.timedelta(days = i_notification_days),
                    # complete_action: False,
                    'result': Result.WINDOW_EXPIRED_BUMP,
                }
            elif di_action_date - di_notification_date >= datetime.timedelta(days = i_notification_days):
                # Most recent notification valid; notify only (no update to notify date)
                return {
                    'dn_notification_date': di_notification_date,
                    'dn_action_date': di_action_date,
                    # complete_action: False,
                    'result': Result.WINDOW_NORMAL_NOTIFY,
                }
            else:
                # Most recent notification too recent; keep notification date, bump action date
                return {
                    'dn_notification_date': di_notification_date,
                    'dn_action_date': di_notification_date + datetime.timedelta(days = i_notification_days),
                    # complete_action: False,
                    'result': Result.WINDOW_RECENT_BUMP,
                }
    print("ERRORR")

def try_notify(email, message_type, message):
    if owner_email is not None:
        notify_list.append((email, message_type, message))

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
notify_list = []

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
        print("Processing instance {0}".format(instance_id))
        # if "Tags" in instance:
        if "Tags" not in instance:
            instance["Tags"] = {}

        state = instance["State"]["Name"]

        autoscaling_group = ([tag for tag in instance["Tags"] if tag["Key"] == T_AUTOSCALING_GROUP] or [{"Value": None}])[0]["Value"]
        exception =         ([tag for tag in instance["Tags"] if tag["Key"] == T_EXCEPTION] or [{"Value": None}])[0]["Value"]
        
        stop_date =         ([tag for tag in instance["Tags"] if tag["Key"] == T_STOP_DATE] or [{"Value": None}])[0]["Value"]
        terminate_date =  ([tag for tag in instance["Tags"] if tag["Key"] == T_TERMINATE_DATE] or [{"Value": None}])[0]["Value"]
        notification_date = ([tag for tag in instance["Tags"] if tag["Key"] == T_NOTIFICATION_DATE] or [{"Value": None}])[0]["Value"]

        instance_name = ([tag for tag in instance["Tags"] if tag["Key"] == T_NAME] or [{"Value": "NoName"}])[0]["Value"]
        
        # Rough equivalent to coalesce
        owner_email = ([tag for tag in instance["Tags"] if tag["Key"] == T_OWNER_EMAIL] or [{"Value": None}])[0]["Value"] \
            or ([tag for tag in instance["Tags"] if tag["Key"] == T_EMAIL] or [{"Value": None}])[0]["Value"] \
            or ([tag for tag in instance["Tags"] if tag["Key"] == T_DIVVY_OWNER] or [{"Value": None}])[0]["Value"] \
            or ([tag for tag in instance["Tags"] if tag["Key"] == T_DIVVY_LAST_MODIFIED_BY] or [{"Value": None}])[0]["Value"]

        print("{} is {}".format(instance_name, state))

        # TODO: figure out if 'if x is not None' is necessary, or except automatically handles it
        try:
            d_stop_date = datetime.date.fromisoformat(stop_date) if stop_date is not None else D_MAX
        except:
            d_stop_date = D_MAX
        try:
            d_terminate_date = datetime.date.fromisoformat(terminate_date) if terminate_date is not None else D_MAX
        except:
            d_terminate_date = D_MAX

        try:
            d_notification_date = datetime.date.fromisoformat(notification_date) if notification_date is not None else D_MAX
        except:
            d_notification_date = D_MAX

        if autoscaling_group is None:
            if exception is None:
                if state == "running":
                    if not override_stop_date:
                        r = determine_action(d_notification_date, d_stop_date, NOTIFICATION_PERIOD, STOP_ACTION_DAYS)
                        print(r)
                        ec2_update_tag(instance_id, instance_name, region, T_NOTIFICATION_DATE, r['dn_notification_date'])
                        ec2_update_tag(instance_id, instance_name, region, T_STOP_DATE, r['dn_action_date'])

                        message = notify_messages[r['result']].format(
                            action = "STOP",
                            type = "EC2 Instance",
                            instance_id = instance_id,
                            region = region,
                            name = instance_name,
                            date = r['dn_action_date'],
                            tag = T_STOP_DATE,
                        )
                        try_notify(owner_email, str(r['result']), message)

                        if r['result'] is Result.PAST_COMPLETE_ACTION:
                            ec2_stop(instance_id = instance_id, instance_name = instance_name, region = region)
                            ec2_update_tag(instance_id, instance_name, region, T_NOTIFICATION_DATE, d_run_date)
                            ec2_update_tag(instance_id, instance_name, region, T_TERMINATE_DATE, d_run_date + datetime.timedelta(days = TERMINATE_ACTION_DAYS))

                            message = notify_messages[Result.ADD_ACTION_DATE].format(
                                action = "TERMINATE",
                                type = "EC2 Instance",
                                instance_id = instance_id,
                                region = region,
                                name = instance_name,
                                date = d_run_date + datetime.timedelta(days = TERMINATE_ACTION_DAYS),
                                tag = T_TERMINATE_DATE,
                            )
                            try_notify(owner_email, str(r['result']), message)
                    else:
                        ec2_update_tag(instance_id, instance_name, region, T_STOP_DATE, d_run_date + datetime.timedelta(days=STOP_ACTION_DAYS))
                        message = notify_messages[Result.OVERRIDE_ACTION_DATE].format(
                            action = "STOP",
                            type = "EC2 Instance",
                            instance_id = instance_id,
                            region = region,
                            name = instance_name,
                            date = d_run_date + datetime.timedelta(days=STOP_ACTION_DAYS),
                            tag = T_STOP_DATE,
                        )
                        try_notify(owner_email, str(Result.OVERRIDE_ACTION_DATE), message)

                elif state == "stopped":
                    r = determine_action(d_notification_date, d_terminate_date, NOTIFICATION_PERIOD, TERMINATE_ACTION_DAYS)
                    print(r)
                    ec2_update_tag(instance_id, instance_name, region, T_TERMINATE_DATE, r['dn_action_date'])
                    ec2_update_tag(instance_id, instance_name, region, T_NOTIFICATION_DATE, r['dn_notification_date'])

                    if r['result'] is Result.PAST_COMPLETE_ACTION:
                        ec2_terminate(instance_id = instance_id, instance_name = instance_name, region = region)

                    message = notify_messages[r['result']].format(
                        action = "TERMINATE",
                        type = "EC2 Instance",
                        instance_id = instance_id,
                        region = region,
                        name = instance_name,
                        date = r['dn_action_date'],
                        tag = T_TERMINATE_DATE,
                    )
                    try_notify(owner_email, str(r['result']), message)
                else:
                    print("Ignoring {name} [{instance_id}] in region {region} because it is in state {state}".format(
                        name = instance_name,
                        instance_id = instance_id,
                        region = region,
                        state = state))

            else: # Exception exists, add to notify list
                print("Exception exists for instance {0}: {1}".format(instance_id,exception))
                if owner_email is not None:
                    try_notify(owner_email, "exception", "exception placeholder {0} [{1}] in region {2}".format(instance_name, instance_id, region))
                else:
                    try_notify("jlee@confluent.io", "invalid_exception", "invalid_exception placeholder {0} [{1}] in region {2}".format(instance_name, instance_id, region))

        else: # In autoscaling group
            print("Instance {0} is in ASG {1}, skipping".format(instance_id,autoscaling_group))

print("")
print("Today is {}".format(d_run_date))
print("Notification List:")

for item in notify_list:
    print(item)