"""
Salesforce Connector
Able to download Account, Case, Campaign, EmailMessage, Lead
Salesforce returns everything as a list of json.
This saves each entry as a separate file to be partitioned.
Using JWT authorization
https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_auth_key_and_cert.htm
https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_auth_connected_app.htm
"""
import os
from collections import OrderedDict
from dataclasses import dataclass
from email.utils import formatdate
from pathlib import Path
from string import Template
from textwrap import dedent
from typing import Any, Dict, List, Type

from dateutil import parser  # type: ignore

from unstructured.ingest.error import SourceConnectionError
from unstructured.ingest.interfaces import (
    BaseConnector,
    BaseConnectorConfig,
    BaseIngestDoc,
    ConnectorCleanupMixin,
    IngestDocCleanupMixin,
    StandardConnectorConfig,
)
from unstructured.ingest.logger import logger
from unstructured.utils import requires_dependencies


class MissingCategoryError(Exception):
    """There are no categories with that name."""


ACCEPTED_CATEGORIES = ["Account", "Case", "Campaign", "EmailMessage", "Lead"]


EMAIL_TEMPLATE = Template(
    """MIME-Version: 1.0
Date: $date
Message-ID: $message_identifier
Subject: $subject
From: $from_email
To: $to_email
Content-Type: multipart/alternative; boundary="00000000000095c9b205eff92630"
--00000000000095c9b205eff92630
Content-Type: text/plain; charset="UTF-8"
$textbody
--00000000000095c9b205eff92630
Content-Type: text/html; charset="UTF-8"
$htmlbody
--00000000000095c9b205eff92630--
""",
)

ACCOUNT_TEMPLATE = Template(
    """Id: $id
Name: $name
Type: $account_type
Phone: $phone
AccountNumber: $account_number
Website: $website
Industry: $industry
AnnualRevenue: $annual_revenue
NumberOfEmployees: $number_employees
Ownership: $ownership
TickerSymbol: $ticker_symbol
Description: $description
Rating: $rating
DandbCompanyId: $dnb_id
""",
)

LEAD_TEMPLATE = Template(
    """Id: $id
Name: $name
Title: $title
Company: $company
Phone: $phone
Email: $email
Website: $website
Description: $description
LeadSource: $lead_source
Rating: $rating
Status: $status
Industry: $industry
""",
)

CASE_TEMPLATE = Template(
    """Id: $id
Type: $type
Status: $status
Reason: $reason
Origin: $origin
Subject: $subject
Priority: $priority
Description: $description
Comments: $comments
""",
)

CAMPAIGN_TEMPLATE = Template(
    """Id: $id
Name: $name
Type: $type
Status: $status
StartDate: $start_date
EndDate: $end_date
BudgetedCost: $budgeted_cost
ActualCost: $actual_cost
Description: $description
NumberOfLeads: $number_of_leads
NumberOfConvertedLeads: $number_of_converted_leads
""",
)


@dataclass
class SimpleSalesforceConfig(BaseConnectorConfig):
    """Connector specific attributes"""

    categories: List[str]
    username: str
    consumer_key: str
    private_key_path: str
    recursive: bool = False

    @staticmethod
    def parse_folders(folder_str: str) -> List[str]:
        """Parses a comma separated string of Outlook folders into a list."""
        return [x.strip() for x in folder_str.split(",")]

    @requires_dependencies(["simple_salesforce"], extras="salesforce")
    def _get_client(self):
        from simple_salesforce import Salesforce

        return Salesforce(
            username=self.username,
            consumer_key=self.consumer_key,
            privatekey_file=self.private_key_path,
        )


@dataclass
class SalesforceIngestDoc(IngestDocCleanupMixin, BaseIngestDoc):
    record_type: str
    record_id: str
    config: SimpleSalesforceConfig
    registry_name: str = "salesforce"

    def _tmp_download_file(self) -> Path:
        if self.record_type == "EmailMessage":
            record_file = self.record_id + ".eml"
        elif self.record_type in ["Account", "Lead", "Case", "Campaign"]:
            record_file = self.record_id + ".xml"
        else:
            raise MissingCategoryError(
                f"There are no categories with the name: {self.record_type}",
            )
        return Path(self.standard_config.download_dir) / self.record_type / record_file

    @property
    def _output_filename(self) -> Path:
        record_file = self.record_id + ".json"
        return Path(self.standard_config.output_dir) / self.record_type / record_file

    def _create_full_tmp_dir_path(self):
        self._tmp_download_file().parent.mkdir(parents=True, exist_ok=True)

    def _xml_for_record(self, record: OrderedDict) -> str:
        """Creates partitionable xml file from a record"""
        import xml.etree.ElementTree as ET

        def flatten_dict(data, parent, prefix=""):
            for key, value in data.items():
                if isinstance(value, OrderedDict):
                    flatten_dict(value, parent, prefix=f"{prefix}{key}.")
                else:
                    item = ET.Element("item")
                    item.text = f"{prefix}{key}: {value}"
                    parent.append(item)

        root = ET.Element("root")
        flatten_dict(record, root)
        xml_string = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode()
        return xml_string

    def _eml_for_record(self, email_json: Dict[str, Any]) -> str:
        """Recreates standard expected .eml format using template."""
        eml = EMAIL_TEMPLATE.substitute(
            date=formatdate(parser.parse(email_json.get("MessageDate")).timestamp()),
            message_identifier=email_json.get("MessageIdentifier"),
            subject=email_json.get("Subject"),
            from_email=email_json.get("FromAddress"),
            to_email=email_json.get("ToAddress"),
            textbody=email_json.get("TextBody"),
            htmlbody=email_json.get("HtmlBody"),
        )
        return dedent(eml)

    @SourceConnectionError.wrap
    @BaseIngestDoc.skip_if_file_exists
    def get_file(self):
        """Saves individual json records locally."""
        self._create_full_tmp_dir_path()
        logger.debug(f"Writing file {self.record_id} - PID: {os.getpid()}")

        client = self.config._get_client()

        # Get record from Salesforce based on id
        record = client.query_all(
            f"select FIELDS(STANDARD) from {self.record_type} where Id='{self.record_id}'",
        )["records"][0]

        try:
            if self.record_type == "EmailMessage":
                document = self._eml_for_record(record)
            else:
                document = self._xml_for_record(record)

            with open(self._tmp_download_file(), "w") as page_file:
                page_file.write(document)

        except Exception as e:
            logger.error(
                f"Error while downloading and saving file: {self.record_id}.",
            )
            logger.error(e)

    @property
    def filename(self):
        """The filename of the file created from a Salesforce record"""
        return self._tmp_download_file()


class SalesforceConnector(ConnectorCleanupMixin, BaseConnector):
    ingest_doc_cls: Type[SalesforceIngestDoc] = SalesforceIngestDoc
    config: SimpleSalesforceConfig

    def __init__(
        self,
        config: SimpleSalesforceConfig,
        standard_config: StandardConnectorConfig,
    ) -> None:
        super().__init__(standard_config, config)

    def initialize(self):
        pass

    @requires_dependencies(["simple_salesforce"], extras="salesforce")
    def get_ingest_docs(self) -> List[SalesforceIngestDoc]:
        """Get Salesforce Ids for the records.
        Send them to next phase where each doc gets downloaded into the
        appropriate format for partitioning.
        """
        from simple_salesforce.exceptions import SalesforceMalformedRequest

        client = self.config._get_client()

        ingest_docs = []
        for record_type in self.config.categories:
            if record_type not in ACCEPTED_CATEGORIES:
                raise ValueError(f"{record_type} not currently an accepted Salesforce category")

            try:
                # Get ids from Salesforce
                records = client.query_all(
                    f"select Id from {record_type}",
                )
                for record in records["records"]:
                    ingest_docs.append(
                        SalesforceIngestDoc(
                            self.standard_config,
                            self.config,
                            record_type,
                            record["Id"],
                        ),
                    )
            except SalesforceMalformedRequest as e:
                raise SalesforceMalformedRequest(f"Problem with Salesforce query: {e}")

        return ingest_docs