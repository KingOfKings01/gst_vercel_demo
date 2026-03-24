from bs4 import BeautifulSoup
import re

def extract_gstin_data(html):
    soup = BeautifulSoup(html, "html.parser")

    data = {}

    # --- GSTIN ---
    header = soup.find("h4")
    if header:
        match = re.search(r'GSTIN/UIN\s*:\s*([A-Z0-9]+)', header.text)
        if match:
            data["GSTIN"] = match.group(1)

    # --- Helper function to extract label-value pairs ---
    def get_value(label):
        tag = soup.find("strong", string=lambda x: x and label.lower() in x.lower())
        if tag:
            parent = tag.find_parent("p")
            if parent:
                next_p = parent.find_next_sibling("p")
                if next_p:
                    return next_p.text.strip()
        return None

    # --- Basic Fields ---
    data["Legal Name of Business"] = get_value("Legal Name")
    data["Trade Name"] = get_value("Trade Name")
    data["Effective Date of registration"] = get_value("Effective Date")
    data["Constitution of Business"] = get_value("Constitution")
    data["GSTIN / UIN Status"] = get_value("GSTIN / UIN")
    data["Taxpayer Type"] = get_value("Taxpayer Type")

    # --- Administrative Office ---
    admin_section = soup.find("strong", string=lambda x: x and "Administrative Office" in x)
    if admin_section:
        parent_p = admin_section.find_parent()
        if parent_p:
            ul = parent_p.find_next_sibling("ul")
            if ul:
                items = [li.text.strip() for li in ul.find_all("li") if li.text.strip()]
                data["Administrative Office"] = items[-1] if items else None

    # --- Other Office (optional) ---
    other_section = soup.find("strong", string=lambda x: x and "Other Office" in x)
    if other_section:
        parent_p = other_section.find_parent()
        if parent_p:
            ul = parent_p.find_next_sibling("ul")
            if ul:
                items = [li.text.strip() for li in ul.find_all("li") if li.text.strip()]
                data["Other Office"] = items[-1] if items else None

    # --- Principal Place of Business ---
    address_tag = soup.find("p", class_="wordCls")
    if address_tag:
        data["Principal Place of Business"] = address_tag.text.strip()

    # --- Nature Of Core Business Activity ---
    # According to the user, this is inside id="collapseTwo"
    # Structure: <li><span>1. </span>Value</li>
    collapse_two = soup.find(id="collapseTwo")
    if collapse_two:
        li_tags = collapse_two.find_all("li")
        nature_values = []
        for li in li_tags:
            # Clone and remove spans
            # This is to handle the User's request to skip the span tag
            li_copy = BeautifulSoup(str(li), "html.parser").li
            if li_copy:
                for span in li_copy.find_all("span"):
                    span.decompose()
                # Get the remaining text
                text = li_copy.get_text(strip=True)
                if text:
                    nature_values.append(text)
        
        if nature_values:
            data["Nature Of Core Business Activity"] = " / ".join(nature_values)

    return data