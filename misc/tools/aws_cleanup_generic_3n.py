#!/usr/bin/python3
# BY DEFAULT, WILL ONLY RUN AGAINST TEST INSTANCES
# MUST USE --full FLAG TO RUN AGAINST WHOLE ACCOUNT

# On fresh Ubuntu instance, install prereqs:
# sudo apt-get update; sudo apt-get install -y python3-pip;
# python3 -m pip install boto3
import enum
import boto3
import logging
import argparse
import datetime
import json
import requests


###############################
# Global and System Variables #
###############################
# Run only against instances in a specific region, for testing
TEST_REGION_OVERRIDE = [
    "us-east-1",
    "us-east-2",
]

# Run only against instances matching specific tags
TEST_FILTER = [
    {
        "Name": "tag:justin",
        "Values": [
            "test",
        ],
    },
]

SLACK_TOKEN_SECRET_REGION="us-east-1"
SLACK_TOKEN_SECRET_NAME="justin/slack_token"
SLACK_TOKEN_SECRET_KEY="token"
SLACK_CHANNEL_KEY="channel_id"

# Chanenl 

NOTIFICATION_PERIOD_1 = 15
NOTIFICATION_PERIOD_2 = 7
NOTIFICATION_PERIOD_3 = 2

MAX_STOP_DAYS = 62
DEFAULT_STOP_DAYS = 31
MAX_TERMINATE_DAYS = 62
DEFAULT_TERMINATE_DAYS = 31

DEFAULT_SEARCH_FILTER = list()

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
T_STOP_LOGS = "aws_cleaner/stop_notification_log"
T_TERMINATE_DATE = "aws_cleaner/terminate_date"
T_TERMINATE_LOGS = "aws_cleaner/terminate_notification_log"
T_NOTIFICATION_1 = "aws_cleaner/notifications/1"
T_NOTIFICATION_2 = "aws_cleaner/notifications/2"
T_NOTIFICATION_3 = "aws_cleaner/notifications/3"


#####################
# Generic Functions #
#####################
def sort_key(x):
    return " ".join(
        [
            x["email"],
            x["instance_type"],
            x["region"],
            x["action"],
            x["result"],
            x["instance_name"],
        ]
    )


def ec2_update_tag(
    instance_id,
    instance_name,
    region,
    key,
    value,
    old_value,
    args,
):
    # TODO: In the future, could batch this up, for now doing it one at a time
    if args.dry_run:
        logging.info(
            "DRY RUN: Skipping update of tag on {0} [{1}] in region {2}: setting {3} from {5} to {4}".format(
                instance_name,
                instance_id,
                region,
                key,
                value,
                old_value,
            )
        )
    else:
        logging.info(
            "Updating tag on {0} [{1}] in region {2}: setting {3} to {4}".format(
                instance_name,
                instance_id,
                region,
                key,
                value,
                old_value,
            )
        )
        # This is super sloppy; right now we're relying on the fact that this is called after ec2_client has created for the relevant region
        # Later could either pass it in, or create an array of clients for regions
        # str(value) takes care of converting datetime.date to string in isoformat '2024-01-01'
        ec2_client.create_tags(
            Resources=[instance_id],
            Tags=[
                {
                    "Key": key,
                    "Value": str(value),
                }
            ],
        )


def ec2_stop(
    instance_id,
    instance_name,
    region,
    args,
):
    if args.dry_run or args.tag_only:
        logging.info(
            "DRY RUN: Stopping instance {0} [{1}] in region {2}".format(
                instance_name,
                instance_id,
                region,
            )
        )
    else:
        logging.info(
            "Stopping instance {0} [{1}] in region {2}".format(
                instance_name,
                instance_id,
                region,
            )
        )
        ec2_client.stop_instances(InstanceIds=[instance_id])


def ec2_terminate(
    instance_id,
    instance_name,
    region,
    args,
):
    if args.dry_run or args.tag_only:
        logging.info(
            "DRY RUN: Terminating instance {0} [{1}] in region {2}".format(
                instance_name,
                instance_id,
                region,
            )
        )
    else:
        logging.info(
            "Terminating instance {0} [{1}] in region {2}".format(
                instance_name,
                instance_id,
                region,
            )
        )
        ec2_client.terminate_instances(InstanceIds=[instance_id])


def determine_action(
    idn_action_date,
    idn_notification_1,
    idn_notification_2,
    idn_notification_3,
    i_default_days,
    i_max_days,
):
    """
    Takes the following:
    idn_action_date: Currently set action date
    idn_notification_1: Current dn_notification_1
    idn_notification_2: Current dn_notification_2
    idn_notification_3: Current dn_notification_3
    i_default_days: Default number of days
    i_max_days: Max number of days
    Returns dict with the following:
    odn_notification_1: New dn_notification_1
    odn_notification_2: New dn_notification_2
    odn_notification_3: New dn_notification_3
    odn_action_date
    result ENUM
    All actual changes (tags and/or instance modification) occurs in calling code, not here.
    """
    logging.debug(
        "idn_action_date:[{idn_action_date}], idn_notification_1:[{idn_notification_1}], idn_notification_2:[{idn_notification_2}], idn_notification_3:[{idn_notification_3}], i_default_days:[{i_default_days}], i_max_days:[{i_max_days}]".format(
            idn_action_date=idn_action_date,
            idn_notification_1=idn_notification_1,
            idn_notification_2=idn_notification_2,
            idn_notification_3=idn_notification_3,
            i_default_days=i_default_days,
            i_max_days=i_max_days,
        )
    )

    if idn_action_date is None:
        message = "Set unset date"
        return {
            "odn_notification_1": None,
            "odn_notification_2": None,
            "odn_notification_3": None,
            "odn_action_date": d_run_date + datetime.timedelta(days=i_default_days),
            "result": Result.ADD_ACTION_DATE,
        }

    elif idn_action_date - d_run_date > datetime.timedelta(days=i_max_days):
        message = "Set to max"
        return {
            "odn_notification_1": None,
            "odn_notification_2": None,
            "odn_notification_3": None,
            "odn_action_date": d_run_date + datetime.timedelta(days=i_max_days),
            "result": Result.RESET_ACTION_DATE,
        }

    elif idn_action_date <= d_run_date:
        if idn_notification_1 is None:
            message = "Set stop date to today + 3 (missing notifications)"
            return {
                "odn_notification_1": d_run_date,
                "odn_notification_2": None,
                "odn_notification_3": None,
                "odn_action_date": d_run_date + datetime.timedelta(days=3),
                "result": Result.PAST_BUMP_NOTIFICATION_1,
            }
        elif idn_notification_2 is None:
            message = "Set stop date to today + 2 (missing notifications)"
            return {
                "odn_notification_1": idn_notification_1,
                "odn_notification_2": d_run_date,
                "odn_notification_3": None,
                "odn_action_date": d_run_date + datetime.timedelta(days=2),
                "result": Result.PAST_BUMP_NOTIFICATION_2,
            }

        elif idn_notification_3 is None:
            message = "Set stop date to today + 1 (missing notifications)"
            return {
                "odn_notification_1": idn_notification_1,
                "odn_notification_2": idn_notification_2,
                "odn_notification_3": d_run_date,
                "odn_action_date": d_run_date + datetime.timedelta(days=1),
                "result": Result.PAST_BUMP_NOTIFICATION_3,
            }

        else:
            message = "Complete action"
            return {
                "odn_notification_1": dn_notification_1,
                "odn_notification_2": dn_notification_2,
                "odn_notification_3": dn_notification_3,
                "odn_action_date": d_run_date,
                "result": Result.COMPLETE_ACTION,
            }

    else:
        remaining_days = idn_action_date - d_run_date

        if dn_notification_1 is None and remaining_days <= datetime.timedelta(
            days=NOTIFICATION_PERIOD_1
        ):
            message = "Send first notification"
            return {
                "odn_notification_1": d_run_date,
                "odn_notification_2": None,
                "odn_notification_3": None,
                "odn_action_date": idn_action_date,
                "result": Result.SEND_NOTIFICATION_1,
            }

        elif dn_notification_2 is None and remaining_days <= datetime.timedelta(
            days=NOTIFICATION_PERIOD_2
        ):
            message = "Send second notification"
            return {
                "odn_notification_1": dn_notification_1,
                "odn_notification_2": d_run_date,
                "odn_notification_3": None,
                "odn_action_date": idn_action_date,
                "result": Result.SEND_NOTIFICATION_2,
            }

        elif dn_notification_3 is None and remaining_days <= datetime.timedelta(
            days=NOTIFICATION_PERIOD_3
        ):
            message = "Send third notification"
            return {
                "odn_notification_1": dn_notification_1,
                "odn_notification_2": dn_notification_2,
                "odn_notification_3": d_run_date,
                "odn_action_date": idn_action_date,
                "result": Result.SEND_NOTIFICATION_3,
            }

        else:
            message = "Log without notification"
            return {
                "odn_notification_1": dn_notification_1,
                "odn_notification_2": dn_notification_2,
                "odn_notification_3": dn_notification_3,
                "odn_action_date": idn_action_date,
                "result": Result.LOG_NO_NOTIFICATION,
            }


class Result(str, enum.Enum):
    ADD_ACTION_DATE = "add_action_date"
    RESET_ACTION_DATE = "reset_action_date"
    COMPLETE_ACTION = "complete_action"
    TRANSITION_ACTION = "transition_action"
    PAST_BUMP_NOTIFICATION_1 = "past_bump_notification_1"
    PAST_BUMP_NOTIFICATION_2 = "past_bump_notification_2"
    PAST_BUMP_NOTIFICATION_3 = "past_bump_notification_3"

    SEND_NOTIFICATION_1 = "send_notification_1"
    SEND_NOTIFICATION_2 = "send_notification_2"
    SEND_NOTIFICATION_3 = "send_notification_3"
    LOG_NO_NOTIFICATION = "log_no_notification"

    IGNORE_OTHER_STATES = "ignore_other_states"
    SKIP_EXCEPTION = "skip_exception"
    # PAST_EXPIRED_NOTIFICATION   = "past_expired_notification"
    # FUTURE_NORMAL_NOTIFY        = "future_normal_notify"
    # WINDOW_EXPIRED_BUMP         = "window_expired_bump"
    # WINDOW_NORMAL_NOTIFY        = "window_normal_notify"
    # WINDOW_RECENT_BUMP          = "window_recent_bump"
    # OVERRIDE_ACTION_DATE        = "override_action_date"
    # EXCEPTION                   = "exception"


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
    return {
        "email": email,
        "instance_type": instance_type,
        "instance_name": instance_name,
        "instance_id": instance_id,
        "region": region,
        "action": action,
        "tag": tag,
        "result": result,
        "old_date": old_date,
        "new_date": new_date,
        "message": message,
    }


def date_or_none(tags, tag):
    """
    Convert to a datetime.date on the way (or return None)
    """
    try:
        return datetime.date.fromisoformat(tags.get(tag))
    except Exception:
        return None

def slack_send_text(token, channel, text):
    r = requests.post(
        url = "https://slack.com/api/chat.postMessage",
        headers = {"Authorization": "Bearer {}".format(token)},
        json = {
            "channel": channel,
            "text": text,
        }
    )

###############
# Main thread #
###############
if __name__ == "__main__":

    # Parse Arguments
    parser = argparse.ArgumentParser(description="AWS Cleanup Script")
    parser.add_argument(
        "--run-date",
        dest="run_date",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
    )
    parser.add_argument(
        "--tag-only",
        action="store_true",
        dest="tag_only",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        dest="full",
    )
    parser.add_argument(
        "--override-stop-date",
        action="store_true",
        dest="override_stop_date",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        dest="debug",
    )
    args = parser.parse_args()

    # Set log level
    logging.basicConfig(
        format=f"[{id}] %(asctime)s.%(msecs)03d [%(levelname)s]: %(message)s",
        level=logging.DEBUG if args.debug else logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    NOTIFY_MESSAGES = {
        Result.ADD_ACTION_DATE: "ADD_ACTION_DATE: Added {action} date to {state} {instance_type} instance '{instance_name}' [{instance_id}] in region {region}, set to {new_date} (tag [{tag}])",
        Result.RESET_ACTION_DATE: "RESET_ACTION_DATE: Updating {state} {instance_type} instance '{instance_name}' [{instance_id}] in region {region}: {action} date changed from {old_date} to {new_date} (tag [{tag}])",
        Result.COMPLETE_ACTION: "COMPLETE_ACTION: Completed {action} on {state} {instance_type} instance '{instance_name}' [{instance_id}] in region {region} (tag [{tag}])",
        Result.TRANSITION_ACTION: "TRANSITION_ACTION: Added new {action} on {state} {instance_type} instance '{instance_name}' [{instance_id}] in region {region} on {new_date} (tag [{tag}])",
        Result.PAST_BUMP_NOTIFICATION_1: "PAST_BUMP_NOTIFICATION_1: Missing first notification: will {action} {state} {instance_type} instance '{instance_name}' [{instance_id}] in region {region} on {new_date} (previously set to {old_date}) (tag [{tag}])",
        Result.PAST_BUMP_NOTIFICATION_2: "PAST_BUMP_NOTIFICATION_2: Missing second notification: will {action} {state} {instance_type} instance '{instance_name}' [{instance_id}] in region {region} on {new_date} (previously set to {old_date} (tag [{tag}])",
        Result.PAST_BUMP_NOTIFICATION_3: "PAST_BUMP_NOTIFICATION_3: Missing third notification: will {action} {state} {instance_type} instance '{instance_name}' [{instance_id}] in region {region} on {new_date} (previously set to {old_date} (tag [{tag}])",
        Result.SEND_NOTIFICATION_1: "SEND_NOTIFICATION_1: Sending first {action} notification for {state} {instance_type} instance '{instance_name}' [{instance_id}] in region {region}: will {action} on {new_date} (tag [{tag}])",
        Result.SEND_NOTIFICATION_2: "SEND_NOTIFICATION_2: Sending second {action} notification for {state} {instance_type} instance '{instance_name}' [{instance_id}] in region {region}: will {action} on {new_date} (tag [{tag}])",
        Result.SEND_NOTIFICATION_3: "SEND_NOTIFICATION_3: Sending third {action} notification for {state} {instance_type} instance '{instance_name}' [{instance_id}] in region {region}: will {action} on {new_date} (tag [{tag}])",
        Result.LOG_NO_NOTIFICATION: "LOG_NO_NOTIFICATION: Will {action} {state} {instance_type} instance '{instance_name}' [{instance_id}] in region {region} on {new_date} (tag [{tag}])",
        Result.IGNORE_OTHER_STATES: "IGNORE_OTHER_STATES: Ignoring {instance_type} {instance_name} [{instance_id}] in region {region} because its state is {state}",
        Result.SKIP_EXCEPTION: "SKIP_EXCEPTION: Skipping {instance_type} instance '{instance_name}' [{instance_id}] in region {region} because it has {tag} set", # Not currently passing in exception value, because it would require adding a different passed-in parameters to NOTIFY_MESSAGES
        # Result.PAST_EXPIRED_NOTIFICATION   : "PAST_EXPIRED_NOTIFICATION: Updated tag [{tag}]: Will {action} {instance_type} {instance_name} [{instance_id}] in region {region} on or after {date}",
        # Result.FUTURE_NORMAL_NOTIFY        : "FUTURE_NORMAL_NOTIFY:  Will {action} {instance_type} {instance_name} [{instance_id}] in region {region} on or after {date} (tag [{tag}])",
        # Result.WINDOW_EXPIRED_BUMP         : "WINDOW_EXPIRED_BUMP:  Updated tag [{tag}]: will {action} {instance_type} {instance_name} [{instance_id}] in region {region} on or after {date}",
        # Result.WINDOW_NORMAL_NOTIFY        : "WINDOW_NORMAL_NOTIFY:  Will {action} {instance_type} {instance_name} [{instance_id}] in region {region} on or after {date} (tag [{tag}])",
        # Result.WINDOW_RECENT_BUMP          : "WINDOW_RECENT_BUMP:  Updated tag [{tag}]: will {action} {instance_type} {instance_name} [{instance_id}] in region {region} on or after {date}",
        # Result.OVERRIDE_ACTION_DATE        : "OVERRIDE_ACTION_DATE: Updated {action} date (tag [{tag}]) of {date} to {instance_type} {instance_name} [{instance_id}] in region {region}",
        # Result.EXCEPTION                   : "EXCEPTION: {instance_type} {instance_name} [{instance_id}] in region {region} has an exception",
    }

    d_run_date = D_TODAY
    if args.run_date:
        d_run_date = datetime.date.fromisoformat(args.run_date)

    search_filter = DEFAULT_SEARCH_FILTER if args.full else TEST_FILTER

    # Slack notification stuff; could probably put this somewhere up higher?
    # Question: if we are unable to retrieve the Slack token (and maybe send a test message), should we kill the entire process?
    aws_secret_client = boto3.client(service_name="secretsmanager", region_name=SLACK_TOKEN_SECRET_REGION)
    try:
        get_secret_value_response = aws_secret_client.get_secret_value(SecretId=SLACK_TOKEN_SECRET_NAME)
        slack_token = json.loads(get_secret_value_response.get('SecretString')).get(SLACK_TOKEN_SECRET_KEY)
        channel_id = json.loads(get_secret_value_response.get('SecretString')).get(SLACK_CHANNEL_KEY)
    except:
        logging.error("Unable to retrieve Slack token from AWS Secret Manager object {}, key {}, region {}".format(SLACK_TOKEN_SECRET_NAME, SLACK_TOKEN_SECRET_KEY, SLACK_TOKEN_SECRET_REGION))

    logging.info("Using Slack token {}, and generic notification chanenl {}".format(slack_token, channel_id))

    # Main process run
    # 
    # We won't send most stuff to Slack, but use this to validate that connection is okay and indicate the script is starting
    logging.info("Running cleaner on {}".format(d_run_date))
    slack_send_text(slack_token, channel_id, "Running cleaner using run date of {}".format(d_run_date))

    if not args.full:
        # use test region filter
        regions = TEST_REGION_OVERRIDE
        logging.info("Using test regions")
    else:
        ec2 = boto3.client("ec2", region_name="us-east-1")
        logging.info("Getting regions")
        regions = [region["RegionName"] for region in ec2.describe_regions()["Regions"]]

    logging.info("Using regions: {}".format(regions))

    detailed_log = list()

    for region in regions:
        logging.info("Processing region {}".format(region))
        ec2_client = boto3.client("ec2", region_name=region)

        # https://stackoverflow.com/a/952952
        # instances = [reservation["Instances"] for reservation in ec2_client.describe_instances(Filters=justin_filter)["Reservations"]]
        # TODO: Add pagination, maybe (hopefully we don't have more than 500 instance running...)
        ec2_instances = [
            instance
            for reservation in ec2_client.describe_instances(
                MaxResults=500,
                Filters=search_filter,
            )["Reservations"]
            for instance in reservation["Instances"]
        ]

        # https://confluentinc.atlassian.net/wiki/spaces/~457145999/pages/3318745562/Cloud+Spend+Reduction+Proposal+AWS+Solutions+Engineering+Account
        for instance in ec2_instances:
            state = instance["State"]["Name"]
            instance_id = instance["InstanceId"]

            logging.info(
                "Processing {} instance {} in region {}".format(
                    state,
                    instance_id,
                    region,
                )
            )

            if "Tags" not in instance:
                tags = dict()
            else:
                tags = {tag["Key"]: tag["Value"] for tag in instance["Tags"]}

            autoscaling_group = tags.get(T_AUTOSCALING_GROUP)
            exception = tags.get(T_EXCEPTION)

            # 'dn_' means 'either a Datetime.date or None'
            dn_stop_date = date_or_none(tags, T_STOP_DATE)
            dn_terminate_date = date_or_none(tags, T_TERMINATE_DATE)
            dn_notification_1 = date_or_none(tags, T_NOTIFICATION_1)
            dn_notification_2 = date_or_none(tags, T_NOTIFICATION_2)
            dn_notification_3 = date_or_none(tags, T_NOTIFICATION_3)

            instance_name = tags.get(T_NAME)

            # Rough equivalent to coalesce
            owner_email = (
                tags.get(T_OWNER_EMAIL)
                or tags.get(T_EMAIL)
                or tags.get(T_DIVVY_OWNER)
                or tags.get(T_DIVVY_LAST_MODIFIED_BY)
            )

            logging.info("{} is {}".format(instance_name, state))

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
                                (T_STOP_DATE, dn_stop_date, r["odn_action_date"]),
                                (
                                    T_NOTIFICATION_1,
                                    dn_notification_1,
                                    r["odn_notification_1"],
                                ),
                                (
                                    T_NOTIFICATION_2,
                                    dn_notification_2,
                                    r["odn_notification_2"],
                                ),
                                (
                                    T_NOTIFICATION_3,
                                    dn_notification_3,
                                    r["odn_notification_3"],
                                ),
                            ]:
                                if tag[1] != tag[2]:
                                    ec2_update_tag(
                                        instance_id=instance_id,
                                        instance_name=instance_name,
                                        region=region,
                                        key=tag[0],
                                        value=tag[2],
                                        old_value=tag[1],
                                        args=args,
                                    )

                            message = NOTIFY_MESSAGES[r["result"]].format(
                                instance_type="EC2",
                                instance_name=instance_name,
                                instance_id=instance_id,
                                region=region,
                                action="STOP",
                                tag=T_STOP_DATE,
                                old_date=dn_stop_date,
                                new_date=r["odn_action_date"],
                                state=state,
                            )

                            detailed_log.append(
                                add_to_log(
                                    email=owner_email,
                                    instance_type="EC2",
                                    instance_name=instance_name,
                                    instance_id=instance_id,
                                    region=region,
                                    action="STOP",
                                    tag=T_STOP_DATE,
                                    result=r["result"],
                                    old_date=dn_stop_date,
                                    new_date=r["odn_action_date"],
                                    message=message,
                                )
                            )

                            if r["result"] == Result.COMPLETE_ACTION:
                                # On complete:
                                # Up till now, have:
                                # * Left notification tags alone (tags are from stop notifications)
                                # * Added a STOP/COMPLETE ACTION log
                                # Now need to do the following: # TODO FIX THIS LOGIC, something is missing here
                                # * Stop the instance
                                # * TODO: Add "Summary stop tag"
                                # * Add a termination date
                                # * Set notification tags back to None
                                # * Add a TERMINATE/TRANSITION log
                                # * Add a TERMINATE/Add tag log?
                                ec2_stop(
                                    instance_id=instance_id,
                                    instance_name=instance_name,
                                    region=region,
                                    args=args,
                                )

                                ec2_update_tag(
                                    instance_id=instance_id,
                                    instance_name=instance_name,
                                    region=region,
                                    key=T_TERMINATE_DATE,
                                    value=d_run_date
                                    + datetime.timedelta(days=DEFAULT_TERMINATE_DAYS),
                                    old_value=None,
                                    args=args,
                                )

                                # Summary stop log
                                ec2_update_tag(
                                    instance_id=instance_id,
                                    instance_name=instance_name,
                                    region=region,
                                    key=T_STOP_LOGS,
                                    value="notified:{},{},{};stopped:{}".format(
                                        dn_notification_1,
                                        dn_notification_2,
                                        dn_notification_3,
                                        d_run_date,
                                    ),
                                    old_value=None,
                                    args=args,
                                )

                                message = NOTIFY_MESSAGES[
                                    Result.TRANSITION_ACTION
                                ].format(
                                    instance_type="EC2",
                                    instance_name=instance_name,
                                    instance_id=instance_id,
                                    region=region,
                                    action="TERMINATE",
                                    tag=T_TERMINATE_DATE,
                                    old_date=d_run_date, # Date of transition, not new terminate date
                                    new_date=d_run_date + datetime.timedelta(days=DEFAULT_TERMINATE_DAYS), # New terminate date
                                    state="stopped", # Have just stopped the instance
                                )

                                detailed_log.append(
                                    add_to_log(
                                        email=owner_email,
                                        instance_type="EC2",
                                        instance_name=instance_name,
                                        instance_id=instance_id,
                                        region=region,
                                        action="TERMINATE",
                                        tag=T_TERMINATE_DATE,
                                        result=Result.TRANSITION_ACTION,
                                        old_date=None,
                                        new_date=d_run_date
                                        + datetime.timedelta(
                                            days=DEFAULT_TERMINATE_DAYS
                                        ),
                                        message=message,
                                    )
                                )

                                for tag in [
                                    (T_NOTIFICATION_1, dn_notification_1, None),
                                    (T_NOTIFICATION_2, dn_notification_2, None),
                                    (T_NOTIFICATION_3, dn_notification_3, None),
                                ]:
                                    ec2_update_tag(
                                        instance_id=instance_id,
                                        instance_name=instance_name,
                                        region=region,
                                        key=tag[0],
                                        value=tag[2],
                                        old_value=tag[1],
                                        args=args,
                                    )
                        else:
                            pass  # Placeholder for 'override' behavior

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
                                (
                                    T_TERMINATE_DATE,
                                    dn_terminate_date,
                                    r["odn_action_date"],
                                ),
                                (
                                    T_NOTIFICATION_1,
                                    dn_notification_1,
                                    r["odn_notification_1"],
                                ),
                                (
                                    T_NOTIFICATION_2,
                                    dn_notification_2,
                                    r["odn_notification_2"],
                                ),
                                (
                                    T_NOTIFICATION_3,
                                    dn_notification_3,
                                    r["odn_notification_3"],
                                ),
                            ]:
                                if tag[1] != tag[2]:
                                    ec2_update_tag(
                                        instance_id=instance_id,
                                        instance_name=instance_name,
                                        region=region,
                                        key=tag[0],
                                        value=tag[2],
                                        old_value=tag[1],
                                        args=args,
                                    )

                            message = NOTIFY_MESSAGES[r["result"]].format(
                                instance_type="EC2",
                                instance_name=instance_name,
                                instance_id=instance_id,
                                region=region,
                                action="TERMINATE",
                                tag=T_STOP_DATE,
                                old_date=dn_terminate_date,
                                new_date=r["odn_action_date"],
                                state=state,
                            )

                            detailed_log.append(
                                add_to_log(
                                    email=owner_email,
                                    instance_type="EC2",
                                    instance_name=instance_name,
                                    instance_id=instance_id,
                                    region=region,
                                    action="TERMINATE",
                                    tag=T_TERMINATE_DATE,
                                    result=r["result"],
                                    old_date=dn_terminate_date,
                                    new_date=r["odn_action_date"],
                                    message=message,
                                )
                            )

                            if r["result"] == Result.COMPLETE_ACTION:
                                # On complete, terminate the instance
                                ec2_terminate(
                                    instance_id=instance_id,
                                    instance_name=instance_name,
                                    region=region,
                                    args=args,
                                )

                                # Summary stop log
                                ec2_update_tag(
                                    instance_id=instance_id,
                                    instance_name=instance_name,
                                    region=region,
                                    key=T_TERMINATE_LOGS,
                                    value="notified:{},{},{};terminated:{}".format(
                                        dn_notification_1,
                                        dn_notification_2,
                                        dn_notification_3,
                                        d_run_date,
                                    ),
                                    old_value=None,
                                    args=args,
                                )
                                # TODO: Add additional log for this?
                        else:
                            pass  # Placeholder for 'override' behavior

                    else:  # State is not running or stopped
                        message = NOTIFY_MESSAGES[Result.IGNORE_OTHER_STATES].format(
                            instance_type="EC2",
                            instance_name=instance_name,
                            instance_id=instance_id,
                            region=region,
                            action="IGNORE",
                            tag=state,  # This is a hack
                            old_date=d_run_date,
                            new_date=d_run_date,
                            state=state,
                        )

                        detailed_log.append(
                            add_to_log(
                                email=owner_email,
                                instance_type="EC2",
                                instance_name=instance_name,
                                instance_id=instance_id,
                                region=region,
                                action="IGNORE",
                                tag=state,  # again, this is a hack
                                result=Result.IGNORE_OTHER_STATES,
                                old_date=d_run_date,
                                new_date=d_run_date,
                                message=message,
                            )
                        )

                else:  # Exception exists, add to notify list
                    message = NOTIFY_MESSAGES[Result.SKIP_EXCEPTION].format(
                        instance_type="EC2",
                        instance_name=instance_name,
                        instance_id=instance_id,
                        region=region,
                        action="SKIP_EXCEPTION",
                        tag=exception,
                        old_date=d_run_date,
                        new_date=d_run_date,
                        state=state,
                    )

                    detailed_log.append(
                        add_to_log(
                            email=owner_email,
                            instance_type="EC2",
                            instance_name=instance_name,
                            instance_id=instance_id,
                            region=region,
                            action="SKIP_EXCEPTION",
                            tag=exception, # This is a hack
                            result=Result.SKIP_EXCEPTION,
                            old_date=d_run_date,
                            new_date=d_run_date,
                            message=message,
                        )
                    )

            else:  # In autoscaling group
                logging.info(
                    "Instance {0} is in ASG {1}, skipping".format(
                        instance_id,
                        autoscaling_group,
                    )
                )
                # TODO: Add log for these

    logging.info("Today is {}".format(d_run_date))
    # logging.info("Notification List:")

    # Arbitrary sort order, primarily for cleanliness in output:
    # * Email
    # * Type
    # * Region
    # * Action
    # * Result
    # * Name

    ignore_list = sorted(
        [x for x in detailed_log if x["action"] == "IGNORE"],
        key=sort_key,
    )
    stop_list = sorted(
        [x for x in detailed_log if x["action"] == "STOP"],
        key=sort_key,
    )
    terminate_list = sorted(
        [x for x in detailed_log if x["action"] == "TERMINATE"],
        key=sort_key,
    )
    alt_list = sorted(
        [
            x
            for x in detailed_log
            if x["action"]
            not in (
                "IGNORE",
                "STOP",
                "TERMINATE",
            )
        ],
        key=sort_key,
    )

    logging.info("IGNORE List:")
    if ignore_list is not None:
        for item in ignore_list:
            logging.info(item)
            slack_send_text(
                token=slack_token,
                channel=channel_id,
                text="{dryrun}{owner}: {message}".format(
                    dryrun="DRY RUN: " if args.dry_run else "",
                    owner=item["email"],
                    message=item["message"]
                )
            )

    logging.info("STOP List:")
    if stop_list is not None:
        for item in stop_list:
            logging.info(item)
            slack_send_text(
                token=slack_token,
                channel=channel_id,
                text="{dryrun}{owner}: {message}".format(
                    dryrun="DRY RUN: " if args.dry_run else "",
                    owner=item["email"],
                    message=item["message"]
                )
            )

    logging.info("TERMINATE List:")
    if terminate_list is not None:
        for item in terminate_list:
            logging.info(item)
            slack_send_text(
                token=slack_token,
                channel=channel_id,
                text="{dryrun}{owner}: {message}".format(
                    dryrun="DRY RUN: " if args.dry_run else "",
                    owner=item["email"],
                    message=item["message"]
                )
            )

    logging.info("ALTERNATE List:")
    if alt_list is not None:
        for item in alt_list:
            logging.info(item)
            slack_send_text(
                token=slack_token,
                channel=channel_id,
                text="{dryrun}{owner}: {message}".format(
                    dryrun="DRY RUN: " if args.dry_run else "",
                    owner=item["email"],
                    message=item["message"]
                )
            )

