"""MAC 地址厂商（OUI）查询表。

只收录了常见厂商，命中不了就返回"未知厂商"。如果目录下存在
``oui.csv``（IEEE 官方格式：Registry,Assignment,Organization Name,...），
会自动加载并覆盖内置表，这样离线也能支持全量 OUI。
"""

from __future__ import annotations

import csv
import os
import re

# key: MAC 前 6 位十六进制（大写、无分隔符）
BUILTIN: dict[str, str] = {
    # Apple
    "000393": "Apple", "000A27": "Apple", "000A95": "Apple", "000D93": "Apple",
    "001124": "Apple", "0016CB": "Apple", "0017F2": "Apple", "001B63": "Apple",
    "001CB3": "Apple", "001E52": "Apple", "001F5B": "Apple", "0021E9": "Apple",
    "002332": "Apple", "00236C": "Apple", "002500": "Apple", "00254B": "Apple",
    "0026B0": "Apple", "0026BB": "Apple", "003065": "Apple", "003EE1": "Apple",
    "0050E4": "Apple", "006171": "Apple", "0090B1": "Apple", "00A040": "Apple",
    "00C610": "Apple", "00CDB9": "Apple", "00DB70": "Apple", "00F4B9": "Apple",
    "040C39": "Apple", "041552": "Apple", "042665": "Apple", "04489A": "Apple",
    "0452F3": "Apple", "04D3CF": "Apple", "04DB56": "Apple", "04E536": "Apple",
    "04F13E": "Apple", "04F7E4": "Apple", "080007": "Apple", "086D41": "Apple",
    "087045": "Apple", "089E01": "Apple", "08F4AB": "Apple", "0C1539": "Apple",
    "0C3021": "Apple", "0C3E9F": "Apple", "0C4DE9": "Apple", "0C5101": "Apple",
    "0C74C2": "Apple", "0C771A": "Apple", "0CBC9F": "Apple", "101C0C": "Apple",
    "10417F": "Apple", "1093E9": "Apple", "109ADD": "Apple", "10DD90": "Apple",
    "14109F": "Apple", "145A05": "Apple", "1460CB": "Apple", "14BD61": "Apple",
    "180373": "Apple", "183451": "Apple", "186590": "Apple", "189EFC": "Apple",
    "18AF61": "Apple", "18E7F4": "Apple", "18EE69": "Apple", "18F643": "Apple",
    "1C1AC0": "Apple", "1C36BB": "Apple", "1C5CF2": "Apple", "1C9148": "Apple",
    "1CABA7": "Apple", "1CE62B": "Apple", "20768F": "Apple", "2078F0": "Apple",
    "209BCD": "Apple", "20A2E4": "Apple", "20C9D0": "Apple", "24A074": "Apple",
    "24A2E1": "Apple", "24E314": "Apple", "24F094": "Apple", "24F677": "Apple",
    "28CFE9": "Apple", "28E02C": "Apple", "28E14C": "Apple", "28ED6A": "Apple",
    "28F076": "Apple", "2C1F23": "Apple", "2C200B": "Apple", "2C3361": "Apple",
    "2CB43A": "Apple", "2CF0A2": "Apple", "2CF0EE": "Apple", "300C29": "Apple",
    "3025A1": "Apple", "30636B": "Apple", "30F7C5": "Apple", "34363B": "Apple",
    "34A395": "Apple", "34AB37": "Apple", "34C059": "Apple", "34E2FD": "Apple",
    "380F4A": "Apple", "38484C": "Apple", "3866F0": "Apple", "38B54D": "Apple",
    "38C986": "Apple", "38CA49": "Apple", "3C0754": "Apple", "3C2EF9": "Apple",
    "3CAB8E": "Apple", "3CD0F8": "Apple", "3CE072": "Apple", "40331A": "Apple",
    "406C8F": "Apple", "40A6D9": "Apple", "40D32D": "Apple", "440010": "Apple",
    "442A60": "Apple", "44D884": "Apple", "44FB42": "Apple", "483B38": "Apple",
    "4860BC": "Apple", "48746E": "Apple", "48A195": "Apple", "48BF6B": "Apple",
    "48D705": "Apple", "48E9F1": "Apple", "4C3275": "Apple", "4C57CA": "Apple",
    "4C7C5F": "Apple", "4C8D79": "Apple", "4CB199": "Apple", "503237": "Apple",
    "5059C4": "Apple", "50EA6D": "Apple", "542696": "Apple", "5462E2": "Apple",
    "54AE27": "Apple", "54E43A": "Apple", "58B035": "Apple", "5C5948": "Apple",
    "5C95AE": "Apple", "5C969D": "Apple", "5CF5DA": "Apple", "5CF938": "Apple",
    "600308": "Apple", "60334B": "Apple", "606944": "Apple", "60C547": "Apple",
    "60FACD": "Apple", "60FB42": "Apple", "60FEC5": "Apple", "64200C": "Apple",
    "64A3CB": "Apple", "64B9E8": "Apple", "64E682": "Apple", "685B35": "Apple",
    "68A86D": "Apple", "68AE20": "Apple", "68D93C": "Apple", "68DB96": "Apple",
    "68FB7E": "Apple", "6C3E6D": "Apple", "6C4008": "Apple", "6C709F": "Apple",
    "6C72E7": "Apple", "6C8DC1": "Apple", "6C94F8": "Apple", "6CC26B": "Apple",
    "701124": "Apple", "7014A6": "Apple", "703EAC": "Apple", "70480F": "Apple",
    "705681": "Apple", "7073CB": "Apple", "70A2B3": "Apple", "70CD60": "Apple",
    "70DEE2": "Apple", "70ECE4": "Apple", "741BB2": "Apple", "748114": "Apple",
    "74E1B6": "Apple", "74E2F5": "Apple", "7831C1": "Apple", "78321B": "Apple",
    "786C1C": "Apple", "78886D": "Apple", "78A3E4": "Apple", "78CA39": "Apple",
    "78D75F": "Apple", "78FD94": "Apple", "7C11BE": "Apple", "7C6D62": "Apple",
    "7C6DF8": "Apple", "7CC3A1": "Apple", "7CC537": "Apple", "7CD1C3": "Apple",
    "7CF05F": "Apple", "7CFADF": "Apple", "80006E": "Apple", "804971": "Apple",
    "80929F": "Apple", "80B03D": "Apple", "80BE05": "Apple", "80E650": "Apple",
    "80EA96": "Apple", "80ED2C": "Apple", "842999": "Apple", "843835": "Apple",
    "848506": "Apple", "84949A": "Apple", "84B153": "Apple", "84FCFE": "Apple",
    "885395": "Apple", "8863DF": "Apple", "886B6E": "Apple", "88C663": "Apple",
    "88CB87": "Apple", "88E87F": "Apple", "8C006D": "Apple", "8C2937": "Apple",
    "8C2DAA": "Apple", "8C5858": "Apple", "8C7B9D": "Apple", "8C7C92": "Apple",
    "8C8590": "Apple", "8CFABA": "Apple", "9027E4": "Apple", "9060F1": "Apple",
    "907240": "Apple", "90840D": "Apple", "908D6C": "Apple", "90B21F": "Apple",
    "90B931": "Apple", "90C1C6": "Apple", "90FD61": "Apple", "943C96": "Apple",
    "949426": "Apple", "94E96A": "Apple", "94F6A3": "Apple", "9801A7": "Apple",
    "9803D8": "Apple", "985AEB": "Apple", "989E63": "Apple", "98B8E3": "Apple",
    "98D6BB": "Apple", "98E0D9": "Apple", "98F0AB": "Apple", "98FE94": "Apple",
    "9C04EB": "Apple", "9C207B": "Apple", "9C293F": "Apple", "9C35EB": "Apple",
    "9C4FDA": "Apple", "9C84BF": "Apple", "9CE65E": "Apple", "9CF387": "Apple",
    "9CFC01": "Apple", "A01828": "Apple", "A0EDCD": "Apple", "A45E60": "Apple",
    "A46706": "Apple", "A4B197": "Apple", "A4C361": "Apple", "A4D18C": "Apple",
    "A4D1D2": "Apple", "A4F1E8": "Apple", "A85B78": "Apple", "A860B6": "Apple",
    "A8667F": "Apple", "A886DD": "Apple", "A88E24": "Apple", "A8968A": "Apple",
    "A8BB7F": "Apple", "A8FAD8": "Apple", "AC293A": "Apple", "AC3C0B": "Apple",
    "AC61EA": "Apple", "AC7F3E": "Apple", "AC87A3": "Apple", "ACBC32": "Apple",
    "ACCF5C": "Apple", "ACD1B8": "Apple", "ACFBC2": "Apple", "B03495": "Apple",
    "B065BD": "Apple", "B09FBA": "Apple", "B0CA68": "Apple", "B418D1": "Apple",
    "B44BD2": "Apple", "B4F0AB": "Apple", "B8098A": "Apple", "B817C2": "Apple",
    "B844D9": "Apple", "B853AC": "Apple", "B8782E": "Apple", "B8C111": "Apple",
    "B8C75D": "Apple", "B8E856": "Apple", "B8F6B1": "Apple", "B8FF61": "Apple",
    "BC3BAF": "Apple", "BC4CC4": "Apple", "BC52B7": "Apple", "BC5436": "Apple",
    "BC6778": "Apple", "BC6C21": "Apple", "BC926B": "Apple", "BC9FEF": "Apple",
    "BCA920": "Apple", "BCC9D9": "Apple", "C01ADA": "Apple", "C06394": "Apple",
    "C0847A": "Apple", "C0CECD": "Apple", "C0F2FB": "Apple", "C42C03": "Apple",
    "C4B301": "Apple", "C81EE7": "Apple", "C82A14": "Apple", "C8334B": "Apple",
    "C869CD": "Apple", "C88550": "Apple", "C8B5B7": "Apple", "C8BC C8": "Apple",
    "C8E0EB": "Apple", "C8F650": "Apple", "CC088D": "Apple", "CC08E0": "Apple",
    "CC29F5": "Apple", "CC4463": "Apple", "CC785F": "Apple", "CCC760": "Apple",
    "D023DB": "Apple", "D02598": "Apple", "D03311": "Apple", "D0A637": "Apple",
    "D0C5F3": "Apple", "D0E140": "Apple", "D49A20": "Apple", "D4DCCD": "Apple",
    "D4F46F": "Apple", "D8004D": "Apple", "D81D72": "Apple", "D83062": "Apple",
    "D8A25E": "Apple", "D8BB2C": "Apple", "D8CF9C": "Apple", "D8D1CB": "Apple",
    "DC0C5C": "Apple", "DC2B2A": "Apple", "DC2B61": "Apple", "DC3714": "Apple",
    "DC415F": "Apple", "DC86D8": "Apple", "DC9B9C": "Apple", "DCA4CA": "Apple",
    "DCA904": "Apple", "DCD3A2": "Apple", "E05F45": "Apple", "E0ACCB": "Apple",
    "E0B52D": "Apple", "E0B9BA": "Apple", "E0C767": "Apple", "E0C97A": "Apple",
    "E0F5C6": "Apple", "E0F847": "Apple", "E425E7": "Apple", "E48B7F": "Apple",
    "E498D6": "Apple", "E4CE8F": "Apple", "E4E4AB": "Apple", "E8802E": "Apple",
    "E88D28": "Apple", "E8B2AC": "Apple", "E8FBE9": "Apple", "EC3586": "Apple",
    "EC852F": "Apple", "F01898": "Apple", "F02475": "Apple", "F0766F": "Apple",
    "F0989D": "Apple", "F0B0E7": "Apple", "F0B479": "Apple", "F0C1F1": "Apple",
    "F0CBA1": "Apple", "F0DBE2": "Apple", "F0DBF8": "Apple", "F0DCE2": "Apple",
    "F0F61C": "Apple", "F40616": "Apple", "F41BA1": "Apple", "F437B7": "Apple",
    "F45C89": "Apple", "F4F15A": "Apple", "F4F951": "Apple", "F81EDF": "Apple",
    "F82793": "Apple", "F89550": "Apple", "F8FF0F": "Apple", "FC253F": "Apple",
    "FC2A9C": "Apple", "FCE998": "Apple", "FCFC48": "Apple",
    # Samsung
    "0000F0": "Samsung", "001247": "Samsung", "0012FB": "Samsung", "0015B9": "Samsung",
    "001632": "Samsung", "0017C9": "Samsung", "0017D5": "Samsung", "0018AF": "Samsung",
    "001A8A": "Samsung", "001D25": "Samsung", "001DF6": "Samsung", "001E7D": "Samsung",
    "001FCC": "Samsung", "001FCD": "Samsung", "0021D1": "Samsung", "0021D2": "Samsung",
    "002339": "Samsung", "0023D6": "Samsung", "0023D7": "Samsung", "002454": "Samsung",
    "002566": "Samsung", "002567": "Samsung", "002637": "Samsung", "00265D": "Samsung",
    "00265F": "Samsung", "0026E2": "Samsung", "002FD9": "Samsung", "08373D": "Samsung",
    "083D88": "Samsung", "08D42B": "Samsung", "08FD0E": "Samsung", "0C715D": "Samsung",
    "0C8910": "Samsung", "101DC0": "Samsung", "1077B1": "Samsung", "1077B3": "Samsung",
    "10D38A": "Samsung", "1432D1": "Samsung", "14568E": "Samsung", "149F3C": "Samsung",
    "14A364": "Samsung", "14F42A": "Samsung", "1816C9": "Samsung", "181EB0": "Samsung",
    "182195": "Samsung", "18E2C2": "Samsung", "1C5A3E": "Samsung", "1C5A6B": "Samsung",
    "1C62B8": "Samsung", "1C66AA": "Samsung", "1C7B21": "Samsung", "1CAF05": "Samsung",
    "2013E0": "Samsung", "205531": "Samsung", "20D390": "Samsung", "20D5BF": "Samsung",
    "2465A2": "Samsung", "24C696": "Samsung", "24DBED": "Samsung", "24F5AA": "Samsung",
    "24FC E5": "Samsung", "28395E": "Samsung", "28987B": "Samsung", "28BAB5": "Samsung",
    "28CC01": "Samsung", "2C0E3D": "Samsung", "2C4402": "Samsung", "2CAE2B": "Samsung",
    "301966": "Samsung", "30CBF8": "Samsung", "30CDA7": "Samsung", "34145F": "Samsung",
    "3423BA": "Samsung", "342D0D": "Samsung", "34AA8B": "Samsung", "34BE00": "Samsung",
    "34C3AC": "Samsung", "380A94": "Samsung", "380B40": "Samsung", "381DD9": "Samsung",
    "38AA3C": "Samsung", "38D40B": "Samsung", "38EC E4": "Samsung", "3C0518": "Samsung",
    "3C5A37": "Samsung", "3C6200": "Samsung", "3C8BFE": "Samsung", "3CA10D": "Samsung",
    "3CB8B4": "Samsung", "3CDD57": "Samsung", "4023AB": "Samsung", "40D3AE": "Samsung",
    "40F49E": "Samsung", "44783E": "Samsung", "44B3C5": "Samsung", "44E4D9": "Samsung",
    "44F459": "Samsung", "4844F7": "Samsung", "484FBB": "Samsung", "4C3C16": "Samsung",
    "4C6641": "Samsung", "4CA56D": "Samsung", "4CBAA3": "Samsung", "4CDD31": "Samsung",
    "5001BB": "Samsung", "5001D9": "Samsung", "503275": "Samsung", "50A4C8": "Samsung",
    "50CCF8": "Samsung", "50F520": "Samsung", "50FC9F": "Samsung", "54620B": "Samsung",
    "5492BE": "Samsung", "549B12": "Samsung", "54F201": "Samsung", "54FA3B": "Samsung",
    "5C0A5B": "Samsung", "5C2E59": "Samsung", "5C3C27": "Samsung", "5C497D": "Samsung",
    "5C8BFE": "Samsung", "5CA39D": "Samsung", "5CE8B7": "Samsung", "5CF6DC": "Samsung",
    "606944": "Samsung", "608F5C": "Samsung", "60A10A": "Samsung", "60D0FC": "Samsung",
    "64219D": "Samsung", "647791": "Samsung", "64B853": "Samsung", "64DDB5": "Samsung",
    "682737": "Samsung", "68EBAE": "Samsung", "68ED43": "Samsung", "6C2F2C": "Samsung",
    "6C8336": "Samsung", "6CB749": "Samsung", "70288B": "Samsung", "70F927": "Samsung",
    "74142F": "Samsung", "7435DA": "Samsung", "74F2FA": "Samsung", "7811DC": "Samsung",
    "781FDB": "Samsung", "78251A": "Samsung", "78471D": "Samsung", "78521A": "Samsung",
    "78A873": "Samsung", "78ABBB": "Samsung", "78BDBC": "Samsung", "78C3E9": "Samsung",
    "78F7BE": "Samsung", "7C0BC6": "Samsung", "7C1C68": "Samsung", "7C2EA3": "Samsung",
    "7C6193": "Samsung", "7C787E": "Samsung", "7C9122": "Samsung", "7CF854": "Samsung",
    "8018A7": "Samsung", "8025EB": "Samsung", "803C57": "Samsung", "80656D": "Samsung",
    "8096B1": "Samsung", "80B989": "Samsung", "84119E": "Samsung", "8425DB": "Samsung",
    "849866": "Samsung", "84A466": "Samsung", "84B541": "Samsung", "84E0F4": "Samsung",
    "8825A6": "Samsung", "88329B": "Samsung", "8849F0": "Samsung", "8863DF": "Samsung",
    "8895B9": "Samsung",  "8C3AE3": "Samsung", "8C71F8": "Samsung", "8C7712": "Samsung",
    "8CBF A6": "Samsung", "8CC8CD": "Samsung", "8CEA1B": "Samsung", "9000DB": "Samsung",
    "900628": "Samsung", "901A4A": "Samsung", "90633B": "Samsung", "90758D": "Samsung",
    "9097D5": "Samsung", "909F33": "Samsung", "90F1AA": "Samsung", "94101F": "Samsung",
    "943BB0": "Samsung", "943FBB": "Samsung", "9463D1": "Samsung", "9495A0": "Samsung",
    "94B10A": "Samsung", "94D771": "Samsung", "94E979": "Samsung", "94FB29": "Samsung",
    "980C82": "Samsung", "981DFA": "Samsung", "9852B1": "Samsung", "98F428": "Samsung",
    "9C0298": "Samsung", "9C2A83": "Samsung", "9C3AAF": "Samsung", "9C65B0": "Samsung",
    "9C807D": "Samsung", "9C99F8": "Samsung", "9CD35B": "Samsung", "9CE6E7": "Samsung",
    "A00798": "Samsung", "A00BBA": "Samsung", "A02195": "Samsung", "A06090": "Samsung",
    "A07591": "Samsung", "A0821F": "Samsung", "A0CB8B": "Samsung", "A48431": "Samsung",
    "A4B271": "Samsung", "A4EBD3": "Samsung", "A80600": "Samsung", "A80DA3": "Samsung",
    "A82BB9": "Samsung", "A849A5": "Samsung", "A87C01": "Samsung", "A88B8F": "Samsung",
    "A8F274": "Samsung", "AC3613": "Samsung", "AC5A14": "Samsung", "AC5F3E": "Samsung",
    "ACE2D3": "Samsung", "ACEE9E": "Samsung", "B047BF": "Samsung", "B0C4E7": "Samsung",
    "B0DF3A": "Samsung", "B407F9": "Samsung", "B43A28": "Samsung", "B46293": "Samsung",
    "B47443": "Samsung", "B4EF39": "Samsung", "B857D8": "Samsung", "B85E7B": "Samsung",
    "B8BB23": "Samsung", "B8C68E": "Samsung", "B8D9CE": "Samsung", "BC1485": "Samsung",
    "BC20A4": "Samsung", "BC448D": "Samsung", "BC72B1": "Samsung", "BC79AD": "Samsung",
    "BC851F": "Samsung", "BCB1F3": "Samsung", "BCD11F": "Samsung", "C01173": "Samsung",
    "C06599": "Samsung", "C08997": "Samsung", "C0BDD1": "Samsung", "C44202": "Samsung",
    "C45006": "Samsung", "C4576E": "Samsung", "C4731E": "Samsung", "C488E5": "Samsung",
    "C81479": "Samsung", "C819F7": "Samsung", "C83870": "Samsung", "C8A823": "Samsung",
    "C8BA94": "Samsung", "CC051B": "Samsung", "CC07AB": "Samsung", "CC3A61": "Samsung",
    "CC6E A4": "Samsung", "CCBFA3": "Samsung", "CCF9E8": "Samsung", "CCFE3C": "Samsung",
    "D013FD": "Samsung", "D0176A": "Samsung", "D022BE": "Samsung", "D02544": "Samsung",
    "D059E4": "Samsung", "D0667B": "Samsung", "D087E2": "Samsung", "D0C1B1": "Samsung",
    "D0C24E": "Samsung", "D0DF C7": "Samsung", "D0FCCC": "Samsung", "D487D8": "Samsung",
    "D48890": "Samsung", "D4AE05": "Samsung", "D4E8B2": "Samsung", "D831CF": "Samsung",
    "D857EF": "Samsung", "D85B2A": "Samsung", "D890E8": "Samsung", "D8C4E9": "Samsung",
    "D8E0E1": "Samsung", "DC4427": "Samsung", "DC7144": "Samsung", "DC71D0": "Samsung",
    "DCCF96": "Samsung", "DCE2AC": "Samsung", "E0991D": "Samsung", "E0CB1D": "Samsung",
    "E0CBEE": "Samsung", "E0DB10": "Samsung", "E432CB": "Samsung", "E440E2": "Samsung",
    "E458B8": "Samsung", "E458E7": "Samsung", "E492FB": "Samsung", "E4B021": "Samsung",
    "E4E0C5": "Samsung", "E8039A": "Samsung", "E8112E": "Samsung", "E83A12": "Samsung",
    "E8508B": "Samsung", "E89309": "Samsung", "E8B4C8": "Samsung", "E8E5D6": "Samsung",
    "EC107B": "Samsung", "EC1F72": "Samsung", "EC9BF3": "Samsung", "ECE09B": "Samsung",
    "F008F1": "Samsung", "F025B7": "Samsung", "F05A09": "Samsung", "F06BCA": "Samsung",
    "F0E77E": "Samsung", "F0EC39": "Samsung", "F0EE10": "Samsung", "F409D8": "Samsung",
    "F40E22": "Samsung", "F42853": "Samsung", "F437B7": "Samsung", "F4428F": "Samsung",
    "F47B5E": "Samsung", "F49F54": "Samsung", "F4D9FB": "Samsung", "F4DC4D": "Samsung",
    "F8042E": "Samsung", "F83F51": "Samsung", "F849C8": "Samsung", "F877B8": "Samsung",
    "F8D0AC": "Samsung", "FCC734": "Samsung", "FCE8 D4": "Samsung",
    # Xiaomi / 生态链
    "009EC8": "Xiaomi", "04CF8C": "Xiaomi", "0C1DAF": "Xiaomi", "102AB3": "Xiaomi",
    "10A4B9": "Xiaomi", "14F65A": "Xiaomi", "185936": "Xiaomi", "1C9DC2": "Xiaomi",
    "20A783": "Xiaomi", "20E7B6": "Xiaomi", "24DA9B": "Xiaomi", "28D127": "Xiaomi",
    "28E31F": "Xiaomi", "2C55D3": "Xiaomi", "342387": "Xiaomi", "3480B3": "Xiaomi",
    "34CE00": "Xiaomi", "380B40": "Xiaomi", "384B24": "Xiaomi", "38A28C": "Xiaomi",
    "3C47B7": "Xiaomi", "3CCD5D": "Xiaomi", "406218": "Xiaomi", "44C34D": "Xiaomi",
    "44E203": "Xiaomi", "4860BC": "Xiaomi", "48B0D4": "Xiaomi", "4C49E3": "Xiaomi",
    "4CFB45": "Xiaomi", "500F80": "Xiaomi", "5061A6": "Xiaomi", "50EC50": "Xiaomi",
    "540F57": "Xiaomi", "58207D": "Xiaomi", "5C021A": "Xiaomi", "5C99B6": "Xiaomi",
    "5CD4AB": "Xiaomi", "5CF9DD": "Xiaomi", "6021C0": "Xiaomi", "640980": "Xiaomi",
    "64B473": "Xiaomi", "64CC2E": "Xiaomi", "68042B": "Xiaomi", "684A76": "Xiaomi",
    "68AB BC": "Xiaomi", "68DFDD": "Xiaomi", "7049E5": "Xiaomi", "742344": "Xiaomi",
    "74C9A3": "Xiaomi", "7802F8": "Xiaomi", "78117F": "Xiaomi", "78A783": "Xiaomi",
    "78DB2F": "Xiaomi", "7C1DD9": "Xiaomi", "7C49EB": "Xiaomi", "7CD661": "Xiaomi",
    "801E10": "Xiaomi", "807D3A": "Xiaomi", "80AD16": "Xiaomi", "8400D2": "Xiaomi",
    "848B7E": "Xiaomi", "84F3EB": "Xiaomi", "88369D": "Xiaomi", "8C3B32": "Xiaomi",
    "8CBEBE": "Xiaomi", "8CDE52": "Xiaomi", "8CF681": "Xiaomi", "900B47": "Xiaomi",
    "9088FE": "Xiaomi", "90EAF9": "Xiaomi", "94FBB2": "Xiaomi", "9810E8": "Xiaomi",
    "9C99A0": "Xiaomi", "9CD21E": "Xiaomi", "A086C6": "Xiaomi", "A0B4A5": "Xiaomi",
    "A4C138": "Xiaomi", "A8610A": "Xiaomi", "AC3A7A": "Xiaomi", "AC5FEA": "Xiaomi",
    "ACC1EE": "Xiaomi", "B0C745": "Xiaomi", "B0E235": "Xiaomi", "B40566": "Xiaomi",
    "B4E6D2": "Xiaomi", "B8D50B": "Xiaomi", "C0E7BF": "Xiaomi", "C40BCB": "Xiaomi",
    "C46AB7": "Xiaomi", "C81FBE": "Xiaomi", "CC2D1B": "Xiaomi", "D094D0": "Xiaomi",
    "D4970B": "Xiaomi", "D4B6F6": "Xiaomi", "D8F15B": "Xiaomi", "DC44B6": "Xiaomi",
    "E0B94D": "Xiaomi", "E4AAEC": "Xiaomi", "E8ABFA": "Xiaomi", "ECBAFE": "Xiaomi",
    "F0B429": "Xiaomi", "F48B32": "Xiaomi", "F4B1C4": "Xiaomi", "F8A45F": "Xiaomi",
    "FC64BA": "Xiaomi", "FCA13E": "Xiaomi",
    # Huawei / 荣耀
    "001882": "Huawei", "001E10": "Huawei", "002568": "Huawei", "00259E": "Huawei",
    "002EC7": "Huawei", "0034FE": "Huawei", "00664B": "Huawei", "009ACD": "Huawei",
    "00E0FC": "Huawei", "00F8 1C": "Huawei", "0402 1F": "Huawei", "0402 48": "Huawei",
    "041E64": "Huawei", "0425C5": "Huawei", "044F4C": "Huawei", "0456 4C": "Huawei",
    "048C9A": "Huawei", "04B0E7": "Huawei", "04BD70": "Huawei", "04C06F": "Huawei",
    "04E8 96": "Huawei", "04F938": "Huawei", "04FE8D": "Huawei", "0805 81": "Huawei",
    "080D 84": "Huawei", "0819A6": "Huawei", "0831A4": "Huawei", "086361": "Huawei",
    "08E84F": "Huawei", "0C37DC": "Huawei", "0C96BF": "Huawei", "0CD6BD": "Huawei",
    "101B54": "Huawei", "1047 80": "Huawei", "105172": "Huawei", "10C61F": "Huawei",
    "1409 DC": "Huawei", "1413FB": "Huawei", "1430 04": "Huawei", "149D09": "Huawei",
    "14B968": "Huawei", "1836 21": "Huawei", "188B45": "Huawei", "18C58A": "Huawei",
    "18D276": "Huawei", "1C15 1F": "Huawei", "1C1D67": "Huawei", "1C8E5C": "Huawei",
    "1CBDB9": "Huawei", "2008ED": "Huawei", "2016 3D": "Huawei", "202BC1": "Huawei",
    "203D66": "Huawei", "204C03": "Huawei", "2091 48": "Huawei", "20A680": "Huawei",
    "20F3A3": "Huawei", "2400 BA": "Huawei", "240995": "Huawei", "24260A": "Huawei",
    "2469A5": "Huawei", "24DBAC": "Huawei", "24DF6A": "Huawei", "283152": "Huawei",
    "285FDB": "Huawei", "28B448": "Huawei", "2C55D3": "Huawei", "2C9D1E": "Huawei",
    "2CAE2B": "Huawei", "3087D9": "Huawei", "30D17E": "Huawei", "3400A3": "Huawei",
    "340A33": "Huawei", "342912": "Huawei", "344B50": "Huawei", "34A2A2": "Huawei",
    "34B354": "Huawei", "34CDBE": "Huawei", "34E2FD": "Huawei", "380E7B": "Huawei",
    "3822E2": "Huawei", "384C4F": "Huawei", "384608": "Huawei", "388435": "Huawei",
    "38BC01": "Huawei", "38F889": "Huawei", "3C058E": "Huawei", "3C36E4": "Huawei",
    "3C47B7": "Huawei", "3CDFBD": "Huawei", "3CF808": "Huawei", "4000E0": "Huawei",
    "40 4D 8E": "Huawei", "40CBA8": "Huawei", "44006F": "Huawei", "4419B6": "Huawei",
    "4423 7C": "Huawei", "4459E4": "Huawei", "44C346": "Huawei", "44D791": "Huawei",
    "480031": "Huawei", "48435A": "Huawei", "487B6B": "Huawei", "48AD08": "Huawei",
    "48DB50": "Huawei", "4C1FCC": "Huawei", "4C5499": "Huawei", "4C8BEF": "Huawei",
    "4CA35F": "Huawei", "4CB16C": "Huawei", "50018B": "Huawei", "503DE5": "Huawei",
    "505DAC": "Huawei", "506AB8": "Huawei", "50A72B": "Huawei", "5425EA": "Huawei",
    "5439DF": "Huawei", "5489 98": "Huawei", "54A51B": "Huawei", "54C4 15": "Huawei",
    "581F28": "Huawei", "5821 41": "Huawei", "58 2A F8": "Huawei", "5C4CA9": "Huawei",
    "5C7D5E": "Huawei", "5CA86A": "Huawei", "5CB395": "Huawei", "5CF96A": "Huawei",
    "600B03": "Huawei", "6021 31": "Huawei", "605D 8A": "Huawei", "60DE44": "Huawei",
    "643E8C": "Huawei", "6456 4D": "Huawei", "649C 6F": "Huawei", "64A651": "Huawei",
    "6805CA": "Huawei", "6889C1": "Huawei", "68A0F6": "Huawei", "68CC6E": "Huawei",
    "68E8 4B": "Huawei", "6C0E0D": "Huawei", "6C4B 90": "Huawei", "6C8B2F": "Huawei",
    "6CA23A": "Huawei", "6CB749": "Huawei", "7005 3D": "Huawei", "7037 5B": "Huawei",
    "7054F5": "Huawei", "70723C": "Huawei", "70A8E3": "Huawei", "70C4 3F": "Huawei",
    "70D931": "Huawei", "70F9 6C": "Huawei", "7427EA": "Huawei", "7436 8C": "Huawei",
    "74A0 6D": "Huawei", "74A5 28": "Huawei", "74E28B": "Huawei", "7810 3B": "Huawei",
    "781DBA": "Huawei", "78446C": "Huawei", "786A89": "Huawei", "7895 25": "Huawei",
    "78B4 6A": "Huawei", "78D752": "Huawei", "78F5FD": "Huawei", "7C00 4A": "Huawei",
    "7C11CB": "Huawei", "7C6097": "Huawei", "7C7D3D": "Huawei", "7CA23E": "Huawei",
    "7CB15D": "Huawei", "7CB7 3B": "Huawei", "7CD9A0": "Huawei", "8004 8F": "Huawei",
    "8071 7B": "Huawei", "8093 6E": "Huawei", "80B686": "Huawei", "80D09B": "Huawei",
    "80FB06": "Huawei", "8404 1F": "Huawei", "8425 9F": "Huawei", "843E92": "Huawei",
    "845B12": "Huawei", "84A8E4": "Huawei", "84DBAC": "Huawei", "883F 0A": "Huawei",
    "8863 9C": "Huawei", "8897 35": "Huawei", "88A2D7": "Huawei", "88CE 3F": "Huawei",
    "88E3AB": "Huawei", "8C0D76": "Huawei", "8C34FD": "Huawei", "8C4B14": "Huawei",
    "8CEBC6": "Huawei", "8CF7 10": "Huawei", "9002A9": "Huawei", "9017AC": "Huawei",
    "902B34": "Huawei", "904E2B": "Huawei", "9067 1C": "Huawei", "9073 41": "Huawei",
    "90C7 D8": "Huawei", "90E6 17": "Huawei", "9404 9B": "Huawei", "940E 6C": "Huawei",
    "9439 4C": "Huawei", "945B 8D": "Huawei", "9465 8C": "Huawei", "9495 A0": "Huawei",
    "94DBDA": "Huawei", "94E2 86": "Huawei", "94FE 22": "Huawei", "980D 2E": "Huawei",
    "982D 56": "Huawei", "9846 8A": "Huawei", "986A 4A": "Huawei", "989C 87": "Huawei",
    "98E7F4": "Huawei", "9C28EF": "Huawei", "9C3A AF": "Huawei", "9C4E 20": "Huawei",
    "9C5CF9": "Huawei", "9C741A": "Huawei", "9C7D A6": "Huawei", "9CA1 2C": "Huawei",
    "9CB2B2": "Huawei", "9CC172": "Huawei", "A00B BA": "Huawei", "A0DF15": "Huawei",
    "A0F479": "Huawei", "A417 8E": "Huawei", "A448 26": "Huawei", "A47174": "Huawei",
    "A499 47": "Huawei", "A4BA76": "Huawei", "A4CAA0": "Huawei", "A80D 6E": "Huawei",
    "A85840": "Huawei", "A897 DC": "Huawei", "A8C4 3C": "Huawei", "A8F5AC": "Huawei",
    "AC44F2": "Huawei", "AC4E91": "Huawei", "AC6089": "Huawei", "AC751D": "Huawei",
    "AC8D14": "Huawei", "ACE87E": "Huawei", "B014 08": "Huawei", "B05B67": "Huawei",
    "B089 00": "Huawei", "B0989F": "Huawei", "B0E5ED": "Huawei", "B41513": "Huawei",
    "B43A 45": "Huawei", "B440A4": "Huawei", "B49842": "Huawei", "B4CD27": "Huawei",
    "B4F58E": "Huawei", "B820 8E": "Huawei", "B83A 5A": "Huawei", "B88687": "Huawei",
    "B894 D9": "Huawei", "B8BC1B": "Huawei", "B8D4 E7": "Huawei", "BC25 E0": "Huawei",
    "BC3F D4": "Huawei", "BC7670": "Huawei", "BCE0 9D": "Huawei", "C07009": "Huawei",
    "C0E4 22": "Huawei", "C4072F": "Huawei", "C40B31": "Huawei", "C4473F": "Huawei",
    "C455 C4": "Huawei", "C4D8 91": "Huawei", "C4F081": "Huawei", "C805 23": "Huawei",
    "C814 51": "Huawei", "C81F EA": "Huawei", "C83D D4": "Huawei", "C88D83": "Huawei",
    "C8D15E": "Huawei", "CC0533": "Huawei", "CC1E 97": "Huawei", "CC53B5": "Huawei",
    "CC96 A0": "Huawei", "CCA2 23": "Huawei", "CCB8F1": "Huawei", "CCE1 7F": "Huawei",
    "D02D B3": "Huawei", "D049 7C": "Huawei", "D057 85": "Huawei", "D05794": "Huawei",
    "D06F 82": "Huawei", "D07A BF": "Huawei", "D0C6 5C": "Huawei", "D0D7 83": "Huawei",
    "D0EF 76": "Huawei", "D415 3C": "Huawei", "D440F0": "Huawei", "D461 2E": "Huawei",
    "D46137": "Huawei", "D47B 35": "Huawei", "D494 E8": "Huawei", "D4B1 10": "Huawei",
    "D4E8 B2": "Huawei", "D4F9A1": "Huawei", "D8490B": "Huawei", "D8C7 71": "Huawei",
    "D8D4 3D": "Huawei", "DC094C": "Huawei", "DC23 51": "Huawei", "DC2D 3C": "Huawei",
    "DC33 50": "Huawei", "DC55 83": "Huawei", "DC71 3A": "Huawei", "DC9B D8": "Huawei",
    "DCD2 FC": "Huawei", "DCD9 96": "Huawei", "E024 7F": "Huawei", "E0286D": "Huawei",
    "E0361D": "Huawei", "E097 96": "Huawei", "E0A3 AC": "Huawei", "E0C3F3": "Huawei",
    "E430 22": "Huawei", "E468A3": "Huawei", "E4789D": "Huawei", "E4A7 C5": "Huawei",
    "E4C2D1": "Huawei", "E4FB5D": "Huawei", "E8088B": "Huawei", "E80B 13": "Huawei",
    "E84D D0": "Huawei", "E8AB FA": "Huawei", "E8CD2D": "Huawei", "EC233D": "Huawei",
    "EC388F": "Huawei", "EC4D47": "Huawei", "EC8C9A": "Huawei", "ECCB30": "Huawei",
    "F04347": "Huawei", "F04B 6A": "Huawei", "F0C4 78": "Huawei", "F0E3 B2": "Huawei",
    "F44C 7F": "Huawei", "F45B 73": "Huawei", "F49A B4": "Huawei", "F4C7 14": "Huawei",
    "F4CB52": "Huawei", "F4DC F9": "Huawei", "F4E3FB": "Huawei", "F801 13": "Huawei",
    "F83D FF": "Huawei", "F84A BF": "Huawei", "F86B D9": "Huawei", "F89A 78": "Huawei",
    "F8E8 11": "Huawei", "FC48EF": "Huawei", "FC75 E1": "Huawei", "FCE3 3C": "Huawei",
    # TP-Link
    "001478": "TP-Link", "0019E0": "TP-Link", "001D0F": "TP-Link", "001E8C": "TP-Link",
    "002127": "TP-Link", "0023CD": "TP-Link", "002586": "TP-Link", "002719": "TP-Link",
    "0418D6": "TP-Link", "0866 98": "TP-Link", "08EA44": "TP-Link", "0C8063": "TP-Link",
    "0C82 68": "TP-Link", "1027F5": "TP-Link", "1062EB": "TP-Link", "10FEA9": "TP-Link",
    "1409 DC": "TP-Link", "14CC20": "TP-Link", "14CF92": "TP-Link", "14E6E4": "TP-Link",
    "18A6F7": "TP-Link", "1C3BF3": "TP-Link", "1C61B4": "TP-Link", "1CFA68": "TP-Link",
    "206BE7": "TP-Link", "20DCE6": "TP-Link", "246081": "TP-Link", "28124E": "TP-Link",
    "28EE52": "TP-Link", "30B5C2": "TP-Link", "30DE4B": "TP-Link", "30FC68": "TP-Link",
    "3408 04": "TP-Link", "3499 71": "TP-Link", "34E894": "TP-Link", "34E911": "TP-Link",
    "3C46D8": "TP-Link", "3C52A1": "TP-Link", "3C84 6A": "TP-Link", "40169F": "TP-Link",
    "40ED00": "TP-Link", "4437E6": "TP-Link", "44B32D": "TP-Link", "44D9E7": "TP-Link",
    "48 0E EC": "TP-Link", "48 22 18": "TP-Link", "48 5D 60": "TP-Link", "48 8F 5A": "TP-Link",
    "4C10D5": "TP-Link", "4C7 9BA": "TP-Link", "4CE173": "TP-Link", "4CEDFB": "TP-Link",
    "500FF5": "TP-Link", "5017FF": "TP-Link", "50C7 BF": "TP-Link", "50D4F7": "TP-Link",
    "50FA84": "TP-Link", "54AF97": "TP-Link", "54C80F": "TP-Link", "54E6FC": "TP-Link",
    "5C63BF": "TP-Link", "5C899A": "TP-Link", "5CA6E6": "TP-Link", "5CF9DD": "TP-Link",
    "60 32 B1": "TP-Link", "60 3A 7C": "TP-Link", "60 91 F3": "TP-Link", "60A4B7": "TP-Link",
    "60E327": "TP-Link", "6466B3": "TP-Link", "646E97": "TP-Link", "68 57 2D": "TP-Link",
    "68FF7B": "TP-Link", "6C5AB0": "TP-Link", "6CE873": "TP-Link", "700F6A": "TP-Link",
    "704F57": "TP-Link", "709F2D": "TP-Link", "70DDA1": "TP-Link", "74 3A EF": "TP-Link",
    "74DA88": "TP-Link", "74EA3A": "TP-Link", "74FE48": "TP-Link", "78 44 76": "TP-Link",
    "78 8C B5": "TP-Link", "78A106": "TP-Link", "78D8 00": "TP-Link", "7C8BCA": "TP-Link",
    "7CB59B": "TP-Link", "80 3F 5D": "TP-Link", "80EA07": "TP-Link", "84160F": "TP-Link",
    "84 16 F9": "TP-Link", "84D81B": "TP-Link", "88 25 93": "TP-Link", "882593": "TP-Link",
    "8C 88 2B": "TP-Link", "8CA6DF": "TP-Link", "8CDE52": "TP-Link", "90 9A 4A": "TP-Link",
    "90F652": "TP-Link", "940C6D": "TP-Link", "940E6C": "TP-Link", "946A77": "TP-Link",
    "94D9B3": "TP-Link", "980D2E": "TP-Link", "9813 33": "TP-Link", "984827": "TP-Link",
    "98DA C4": "TP-Link", "9C53CD": "TP-Link", "9CA2F4": "TP-Link", "9CB6D0": "TP-Link",
    "A0F3C1": "TP-Link", "A40CC3": "TP-Link", "A42BB0": "TP-Link", "A4 2B B0": "TP-Link",
    "A8574E": "TP-Link", "A8 57 4E": "TP-Link", "AC 15 A2": "TP-Link", "AC84C6": "TP-Link",
    "AC9A 96": "TP-Link", "B0487A": "TP-Link", "B0 48 7A": "TP-Link", "B0BE76": "TP-Link",
    "B4B0 24": "TP-Link", "B4B024": "TP-Link", "B8F883": "TP-Link", "BC 46 99": "TP-Link",
    "BC4699": "TP-Link", "C0 06 C3": "TP-Link", "C0 25 E9": "TP-Link", "C0 4A 00": "TP-Link",
    "C0 4A 00": "TP-Link", "C006C3": "TP-Link", "C025E9": "TP-Link", "C04A00": "TP-Link",
    "C46E1F": "TP-Link", "C4 6E 1F": "TP-Link", "C4E984": "TP-Link", "C8 0E 14": "TP-Link",
    "CC32E5": "TP-Link", "CC 32 E5": "TP-Link", "D0 76 50": "TP-Link", "D07650": "TP-Link",
    "D46E0E": "TP-Link", "D80D17": "TP-Link", "D8 07 B6": "TP-Link", "D807B6": "TP-Link",
    "DC 9F DB": "TP-Link", "DC9FDB": "TP-Link", "E028 6D": "TP-Link", "E4C32A": "TP-Link",
    "E4 C3 2A": "TP-Link", "E8 48 B8": "TP-Link", "E848B8": "TP-Link", "E8DE 27": "TP-Link",
    "E8DE27": "TP-Link", "EC 08 6B": "TP-Link", "EC086B": "TP-Link", "EC 88 8F": "TP-Link",
    "EC888F": "TP-Link", "F0 9F C2": "TP-Link", "F09FC2": "TP-Link", "F4 EC 38": "TP-Link",
    "F4EC38": "TP-Link", "F4F2 6D": "TP-Link", "F4F26D": "TP-Link", "F8 1A 67": "TP-Link",
    "F81A67": "TP-Link", "FC 7C 02": "TP-Link", "FC7C02": "TP-Link",
    # Intel
    "001111": "Intel", "0012F0": "Intel", "001302": "Intel", "001320": "Intel",
    "0013CE": "Intel", "0013E8": "Intel", "001500": "Intel", "001517": "Intel",
    "0016EA": "Intel", "0016EB": "Intel", "0018DE": "Intel", "0019D1": "Intel",
    "0019D2": "Intel", "001B21": "Intel", "001B77": "Intel", "001CC0": "Intel",
    "001DE0": "Intel", "001E64": "Intel", "001E67": "Intel", "001F3B": "Intel",
    "001F3C": "Intel", "0021 5C": "Intel", "00215C": "Intel", "00215D": "Intel",
    "00216A": "Intel", "00216B": "Intel", "0022FA": "Intel", "0022FB": "Intel",
    "002315": "Intel", "002332": "Intel", "0024D6": "Intel", "0024D7": "Intel",
    "0026C6": "Intel", "0026C7": "Intel", "00270E": "Intel", "002710": "Intel",
    "00AA00": "Intel", "00AA01": "Intel", "00AA02": "Intel", "00D0B7": "Intel",
    "04 54 53": "Intel", "045453": "Intel", "0C8BFD": "Intel", "0CD292": "Intel",
    "100BA9": "Intel", "101F74": "Intel", "10F005": "Intel", "18 03 73": "Intel",
    "1C4D70": "Intel", "24418C": "Intel", "28D244": "Intel", "2C337A": "Intel",
    "30 3A 64": "Intel", "303A64": "Intel", "3417EB": "Intel", "34 02 86": "Intel",
    "340286": "Intel", "34E12D": "Intel", "3C 95 09": "Intel", "3C9509": "Intel",
    "40 25 C2": "Intel", "4025C2": "Intel", "442A60": "Intel", "44 85 00": "Intel",
    "448500": "Intel", "48 45 20": "Intel", "484520": "Intel", "4851B7": "Intel",
    "48F17F": "Intel", "4C 34 88": "Intel", "4C3488": "Intel", "4C79BA": "Intel",
    "50 76 AF": "Intel", "5076AF": "Intel", "54 27 1D": "Intel", "54271D": "Intel",
    "58 91 CF": "Intel", "5891CF": "Intel", "5C 51 4F": "Intel", "5C514F": "Intel",
    "5C E0 C5": "Intel", "5CE0C5": "Intel", "60 36 DD": "Intel", "6036DD": "Intel",
    "60 57 18": "Intel", "605718": "Intel", "60 67 20": "Intel", "606720": "Intel",
    "64 80 99": "Intel", "648099": "Intel", "68 05 CA": "Intel", "6805CA": "Intel",
    "6C 29 95": "Intel", "6C2995": "Intel", "6C 88 14": "Intel", "6C8814": "Intel",
    "70 1C E7": "Intel", "701CE7": "Intel", "74 E5 0B": "Intel", "74E50B": "Intel",
    "78 92 9C": "Intel", "78929C": "Intel", "7C 5C F8": "Intel", "7C5CF8": "Intel",
    "7C 7A 91": "Intel", "7C7A91": "Intel", "80 19 34": "Intel", "801934": "Intel",
    "80 86 F2": "Intel", "8086F2": "Intel", "84 3A 4B": "Intel", "843A4B": "Intel",
    "88 53 2E": "Intel", "88532E": "Intel", "8C 16 45": "Intel", "8C1645": "Intel",
    "8C 55 4A": "Intel", "8C554A": "Intel", "90 49 FA": "Intel", "9049FA": "Intel",
    "94 65 9C": "Intel", "94659C": "Intel", "94 C6 91": "Intel", "94C691": "Intel",
    "98 4F EE": "Intel", "984FEE": "Intel", "9C 4E 36": "Intel", "9C4E36": "Intel",
    "9C B6 D0": "Intel", "A0 36 9F": "Intel", "A0369F": "Intel", "A0 88 69": "Intel",
    "A08869": "Intel", "A4 4E 31": "Intel", "A44E31": "Intel", "A4 C4 94": "Intel",
    "A4C494": "Intel", "A8 6B AD": "Intel", "A86BAD": "Intel", "AC 7B A1": "Intel",
    "AC7BA1": "Intel", "AC FD CE": "Intel", "ACFDCE": "Intel", "B4 6B FC": "Intel",
    "B46BFC": "Intel", "B4 96 91": "Intel", "B49691": "Intel", "B8 08 CF": "Intel",
    "B808CF": "Intel", "BC 0F 9B": "Intel", "BC0F9B": "Intel", "BC 77 37": "Intel",
    "BC7737": "Intel", "C0 3F D5": "Intel", "C03FD5": "Intel", "C8 34 8D": "Intel",
    "C8348D": "Intel", "C8 F7 50": "Intel", "C8F750": "Intel", "CC 2F 71": "Intel",
    "CC2F71": "Intel", "D0 57 7C": "Intel", "D0577C": "Intel", "D4 25 CC": "Intel",
    "D425CC": "Intel", "D8 FC 93": "Intel", "D8FC93": "Intel", "DC 53 60": "Intel",
    "DC5360": "Intel", "E4 A4 71": "Intel", "E4A471": "Intel", "E4 B3 18": "Intel",
    "E4B318": "Intel", "E8 2A 44": "Intel", "E82A44": "Intel", "E8 B1 FC": "Intel",
    "E8B1FC": "Intel", "EC F4 BB": "Intel", "ECF4BB": "Intel", "F0 DE F1": "Intel",
    "F0DEF1": "Intel", "F4 8C 50": "Intel", "F48C50": "Intel", "F8 16 54": "Intel",
    "F81654": "Intel", "F8 63 3F": "Intel", "F8633F": "Intel", "FC AA 14": "Intel",
    "FCAA14": "Intel", "FC F8 AE": "Intel", "FCF8AE": "Intel",
    # Espressif（ESP8266/ESP32 物联网模块）
    "18FE34": "Espressif", "240AC4": "Espressif", "246F28": "Espressif",
    "2CF432": "Espressif", "308398": "Espressif", "30AEA4": "Espressif",
    "3C71BF": "Espressif", "441793": "Espressif", "48 3F DA": "Espressif",
    "483FDA": "Espressif", "4C11AE": "Espressif", "5CCF7F": "Espressif",
    "600194": "Espressif", "68C63A": "Espressif", "7C9EBD": "Espressif",
    "7CDFA1": "Espressif", "807D3A": "Espressif", "84CC A8": "Espressif",
    "84CCA8": "Espressif", "84F3EB": "Espressif", "8CAAB5": "Espressif",
    "90 38 0C": "Espressif", "90380C": "Espressif", "94B97E": "Espressif",
    "A020A6": "Espressif", "A4CF12": "Espressif", "AC67B2": "Espressif",
    "B4E62D": "Espressif", "B8D61A": "Espressif", "BCDDC2": "Espressif",
    "C44F33": "Espressif", "C4DD57": "Espressif", "CC50E3": "Espressif",
    "D8A01D": "Espressif", "D8F15B": "Espressif", "DC4F22": "Espressif",
    "E0 98 06": "Espressif", "E09806": "Espressif", "E8DB84": "Espressif",
    "EC FA BC": "Espressif", "ECFABC": "Espressif", "F0 08 D1": "Espressif",
    "F008D1": "Espressif", "F4CFA2": "Espressif",
    # Raspberry Pi
    "28CDC1": "Raspberry Pi", "2CCF67": "Raspberry Pi", "3A3541": "Raspberry Pi",
    "5CCF7F": "Raspberry Pi", "B827EB": "Raspberry Pi", "D83ADD": "Raspberry Pi",
    "DCA632": "Raspberry Pi", "E45F01": "Raspberry Pi", "DCA6 32": "Raspberry Pi",
    "88A29E": "Raspberry Pi", "E4 5F 01": "Raspberry Pi",
    # Realtek / 通用网卡
    "00E04C": "Realtek", "525400": "QEMU 虚拟机",
    "001C42": "Realtek", "08BFB8": "Realtek",
    # 虚拟化
    "000C29": "VMware", "005056": "VMware", "001C14": "VMware", "0050 56": "VMware",
    "080027": "VirtualBox", "0A0027": "VirtualBox", "00155D": "Hyper-V",
    "001DD8": "Microsoft Hyper-V", "00 15 5D": "Hyper-V",
    "0242AC": "Docker 虚拟网卡（IP 段 172.17+）",
    # 网络设备 / 其他
    "0006 5B": "Dell", "00188B": "Dell", "00219B": "Dell", "0024E8": "Dell",
    "14B31F": "Dell", "18A99B": "Dell", "1866DA": "Dell", "18DBF2": "Dell",
    "20040F": "Dell", "246E96": "Dell", "2C6002": "Dell", "3417EB": "Dell",
    "44A842": "Dell", "4C7625": "Dell", "509A4C": "Dell", "544810": "Dell",
    "5CF9DD": "Dell", "6C2B59": "Dell", "7845C4": "Dell", "84 2B 2B": "Dell",
    "842B2B": "Dell", "8CCE4E": "Dell", "90B11C": "Dell", "9840BB": "Dell",
    "A41F72": "Dell", "B083FE": "Dell", "B8 2A 72": "Dell", "B82A72": "Dell",
    "B8AC6F": "Dell", "C81F66": "Dell", "D067E5": "Dell", "D4 AE 52": "Dell",
    "D4AE52": "Dell", "D4BED9": "Dell", "E0DB55": "Dell", "EC F4 BB": "Dell",
    "F04DA2": "Dell", "F48E38": "Dell", "F8B156": "Dell", "F8BC12": "Dell",
    "F8DB88": "Dell",
    "000D0B": "Buffalo", "001601": "Buffalo", "001D73": "Buffalo", "106F3F": "Buffalo",
    "4CE676": "Buffalo", "DC FB 02": "Buffalo", "DCFB02": "Buffalo",
    "001B2F": "NETGEAR", "0024B2": "NETGEAR", "0026F2": "NETGEAR", "20E52A": "NETGEAR",
    "28C68E": "NETGEAR", "2C3033": "NETGEAR", "30469A": "NETGEAR", "3894ED": "NETGEAR",
    "3C37 86": "NETGEAR", "3C3786": "NETGEAR", "405D82": "NETGEAR", "44944A": "NETGEAR",
    "4C60DE": "NETGEAR", "6CB0CE": "NETGEAR", "744401": "NETGEAR", "841B5E": "NETGEAR",
    "9C3DCF": "NETGEAR", "9CD36D": "NETGEAR", "A00460": "NETGEAR", "A040A0": "NETGEAR",
    "B03956": "NETGEAR", "B07FB9": "NETGEAR", "C03F0E": "NETGEAR", "C43DC7": "NETGEAR",
    "CC40D0": "NETGEAR", "E0469A": "NETGEAR", "E091F5": "NETGEAR", "E4F4C6": "NETGEAR",
    "E8FC AF": "NETGEAR", "E8FCAF": "NETGEAR", "F87394": "NETGEAR",
    "0024A5": "Buffalo", "001C10": "Cisco-Linksys", "002129": "Cisco-Linksys",
    "001839": "Cisco-Linksys", "001A70": "Cisco-Linksys", "002369": "Cisco-Linksys",
    "0025 9C": "Cisco-Linksys", "00259C": "Cisco-Linksys", "48F8B3": "Cisco-Linksys",
    "680235": "Cisco-Linksys", "C0C1C0": "Cisco-Linksys", "E89F80": "Cisco-Linksys",
    "001217": "Cisco", "001A30": "Cisco", "001B0C": "Cisco", "001B2A": "Cisco",
    "001BD4": "Cisco", "001E13": "Cisco", "0021A0": "Cisco", "002290": "Cisco",
    "0023EB": "Cisco", "0024C4": "Cisco", "0025B4": "Cisco", "002608": "Cisco",
    "08CC68": "Cisco", "0CD996": "Cisco", "1CE85D": "Cisco", "2894 0B": "Cisco",
    "28940B": "Cisco", "2C3F38": "Cisco", "2C542D": "Cisco", "30E4DB": "Cisco",
    "3C0E23": "Cisco", "4403A7": "Cisco", "4C0082": "Cisco", "5057A8": "Cisco",
    "54781A": "Cisco", "58971E": "Cisco", "5C5015": "Cisco", "6400F1": "Cisco",
    "6C2056": "Cisco", "70105C": "Cisco", "74A02F": "Cisco", "7C69F6": "Cisco",
    "84B261": "Cisco", "8C604F": "Cisco", "9C57AD": "Cisco", "A0ECF9": "Cisco",
    "A46C2A": "Cisco", "A80C0D": "Cisco", "B000B4": "Cisco", "B4A4E3": "Cisco",
    "B4DE31": "Cisco", "C067AF": "Cisco", "C4143C": "Cisco", "C80084": "Cisco",
    "CC7F75": "Cisco", "D0574C": "Cisco", "D4A02A": "Cisco", "DCA5F4": "Cisco",
    "E05FB9": "Cisco", "E8B748": "Cisco", "EC3091": "Cisco", "F02929": "Cisco",
    "F09E63": "Cisco", "F4ACC1": "Cisco", "F8 4F 57": "Cisco", "F84F57": "Cisco",
    "0024 7B": "AzureWave", "00247B": "AzureWave", "28C2DD": "AzureWave",
    "44D2 44": "AzureWave", "44D244": "AzureWave", "6C71D9": "AzureWave",
    "80C5F2": "AzureWave", "9C B6 D0": "AzureWave", "AC E0 10": "AzureWave",
    "ACE010": "AzureWave", "D0C1B1": "AzureWave", "E0B9A5": "AzureWave",
    "F05C77": "AzureWave", "FCD848": "AzureWave",
    "0017 88": "Signify (Philips Hue)", "001788": "Signify (Philips Hue)",
    "ECB5FA": "Signify (Philips Hue)", "001A22": "eQ-3 (HomeMatic)",
    "34CE00": "索尼", "0024BE": "索尼", "0013A9": "索尼", "0019C5": "索尼",
    "0025E7": "索尼", "30F9ED": "索尼", "54 42 49": "索尼", "544249": "索尼",
    "78843C": "索尼", "A0E453": "索尼", "B8F934": "索尼", "F8D0AC": "索尼",
    "00 04 20": "索尼", "000420": "索尼", "001DBA": "索尼", "001F 5B": "索尼",
    "0024 7B": "索尼", "FC0FE6": "索尼",
    "0017 3F": "Nintendo", "00173F": "Nintendo", "0017AB": "Nintendo",
    "0019 1D": "Nintendo", "00191D": "Nintendo", "001B7A": "Nintendo",
    "001BDC": "Nintendo", "001CBA": "Nintendo", "001E35": "Nintendo",
    "001F32": "Nintendo", "002147": "Nintendo", "00224C": "Nintendo",
    "0023CC": "Nintendo", "002444": "Nintendo", "0025A0": "Nintendo",
    "344BE8": "Nintendo", "40D28A": "Nintendo", "58BDAE": "Nintendo",
    "5C521E": "Nintendo", "78A2A0": "Nintendo", "8CCDE8": "Nintendo",
    "98363D": "Nintendo", "9CE635": "Nintendo", "B88AEC": "Nintendo",
    "CC9E00": "Nintendo", "E00C7F": "Nintendo",
    "00 1B A9": "Brother", "001BA9": "Brother", "0080 77": "Brother",
    "008077": "Brother", "30 05 5C": "Brother", "30055C": "Brother",
    "3C2A F4": "Brother", "3C2AF4": "Brother", "9C AE D3": "Brother",
    "9CAED3": "Brother", "AC 44 F2": "Brother",
    "00 00 48": "Seiko Epson", "000048": "Seiko Epson", "00 26 AB": "Seiko Epson",
    "0026AB": "Seiko Epson", "38 1A 52": "Seiko Epson", "381A52": "Seiko Epson",
    "44 D2 44": "Seiko Epson", "64 EB 8C": "Seiko Epson", "64EB8C": "Seiko Epson",
    "A4 EE 57": "Seiko Epson", "A4EE57": "Seiko Epson", "DC CC E6": "Seiko Epson",
    "DCCCE6": "Seiko Epson",
    "00 1E 0B": "ASUSTek", "001E0B": "ASUSTek", "00 1F C6": "ASUSTek",
    "001FC6": "ASUSTek", "00 22 15": "ASUSTek", "002215": "ASUSTek",
    "00 23 54": "ASUSTek", "002354": "ASUSTek", "00 24 8C": "ASUSTek",
    "00248C": "ASUSTek", "00 26 18": "ASUSTek", "002618": "ASUSTek",
    "04 D4 C4": "ASUSTek", "04D4C4": "ASUSTek", "08 60 6E": "ASUSTek",
    "08606E": "ASUSTek", "08 62 66": "ASUSTek", "086266": "ASUSTek",
    "0C 9D 92": "ASUSTek", "0C9D92": "ASUSTek", "10 BF 48": "ASUSTek",
    "10BF48": "ASUSTek", "10C37B": "ASUSTek", "14 DA E9": "ASUSTek",
    "14DAE9": "ASUSTek", "14 DD A9": "ASUSTek", "14DDA9": "ASUSTek",
    "1C 87 2C": "ASUSTek", "1C872C": "ASUSTek", "2C 4D 54": "ASUSTek",
    "2C4D54": "ASUSTek", "2C56 DC": "ASUSTek", "2C56DC": "ASUSTek",
    "30 5A 3A": "ASUSTek", "305A3A": "ASUSTek", "38 D5 47": "ASUSTek",
    "38D547": "ASUSTek", "40 16 7E": "ASUSTek", "40167E": "ASUSTek",
    "44 8A 5B": "ASUSTek", "448A5B": "ASUSTek", "4C ED FB": "ASUSTek",
    "50 46 5D": "ASUSTek", "50465D": "ASUSTek", "54 04 A6": "ASUSTek",
    "5404A6": "ASUSTek", "60 45 CB": "ASUSTek", "6045CB": "ASUSTek",
    "70 4D 7B": "ASUSTek", "704D7B": "ASUSTek", "74 D0 2B": "ASUSTek",
    "74D02B": "ASUSTek", "78 24 AF": "ASUSTek", "7824AF": "ASUSTek",
    "88 D7 F6": "ASUSTek", "88D7F6": "ASUSTek", "9C 5C 8E": "ASUSTek",
    "9C5C8E": "ASUSTek", "AC 22 0B": "ASUSTek", "AC220B": "ASUSTek",
    "AC 9E 17": "ASUSTek", "AC9E17": "ASUSTek", "B0 6E BF": "ASUSTek",
    "B06EBF": "ASUSTek", "BC AE C5": "ASUSTek", "BCAEC5": "ASUSTek",
    "BC EE 7B": "ASUSTek", "BCEE7B": "ASUSTek", "C8 60 00": "ASUSTek",
    "C86000": "ASUSTek", "D0 17 C2": "ASUSTek", "D017C2": "ASUSTek",
    "D8 50 E6": "ASUSTek", "D850E6": "ASUSTek", "E0 3F 49": "ASUSTek",
    "E03F49": "ASUSTek", "E0 CB 4E": "ASUSTek", "E0CB4E": "ASUSTek",
    "F4 6D 04": "ASUSTek", "F46D04": "ASUSTek", "F8 32 E4": "ASUSTek",
    "F832E4": "ASUSTek",
    "0015 5D": "Microsoft", "00155D": "Microsoft", "0017FA": "Microsoft",
    "0017FA": "Microsoft", "002248": "Microsoft", "0022 48": "Microsoft",
    "0050F2": "Microsoft", "2818 78": "Microsoft", "281878": "Microsoft",
    "3C83 B5": "Microsoft", "3C83B5": "Microsoft", "4850 73": "Microsoft",
    "485073": "Microsoft", "58 82 A8": "Microsoft", "5882A8": "Microsoft",
    "60 45 BD": "Microsoft", "6045BD": "Microsoft", "7C1E52": "Microsoft",
    "7C ED 8D": "Microsoft", "7CED8D": "Microsoft", "98 5F D3": "Microsoft",
    "985FD3": "Microsoft", "C8 3F B4": "Microsoft", "C83FB4": "Microsoft",
    "DC B4 C4": "Microsoft", "DCB4C4": "Microsoft",
    "00 1C 42": "Wyse", "001C42": "Wyse",
    "00 08 9B": "ICP Electronics", "00089B": "ICP Electronics",
    "00 1A 79": "Shenzhen", "001A79": "Shenzhen",
    "3C 5A 37": "Shenzhen", "3C5A37": "Shenzhen",
    "00 E0 4C": "Realtek", "00E04C": "Realtek",
    "00 26 82": "Hewlett Packard", "002682": "Hewlett Packard",
    "00 1F 29": "Hewlett Packard", "001F29": "Hewlett Packard",
    "00 21 5A": "Hewlett Packard", "00215A": "Hewlett Packard",
    "00 22 64": "Hewlett Packard", "002264": "Hewlett Packard",
    "00 23 7D": "Hewlett Packard", "00237D": "Hewlett Packard",
    "00 25 B3": "Hewlett Packard", "0025B3": "Hewlett Packard",
    "08 00 09": "Hewlett Packard", "345B63": "Hewlett Packard",
    "34 64 A9": "Hewlett Packard", "3464A9": "Hewlett Packard",
    "3C D9 2B": "Hewlett Packard", "3CD92B": "Hewlett Packard",
    "40 A8 F0": "Hewlett Packard", "40A8F0": "Hewlett Packard",
    "44 1E A1": "Hewlett Packard", "441EA1": "Hewlett Packard",
    "48 0F CF": "Hewlett Packard", "480FCF": "Hewlett Packard",
    "58 20 B1": "Hewlett Packard", "5820B1": "Hewlett Packard",
    "6C C2 17": "Hewlett Packard", "6CC217": "Hewlett Packard",
    "70 5A 0F": "Hewlett Packard", "705A0F": "Hewlett Packard",
    "78 E3 B5": "Hewlett Packard", "78E3B5": "Hewlett Packard",
    "80 C1 6E": "Hewlett Packard", "80C16E": "Hewlett Packard",
    "94 57 A5": "Hewlett Packard", "9457A5": "Hewlett Packard",
    "98 E7 F4": "Hewlett Packard", "9C B6 54": "Hewlett Packard",
    "9CB654": "Hewlett Packard", "A0 1D 48": "Hewlett Packard",
    "A01D48": "Hewlett Packard", "A0 2B B8": "Hewlett Packard",
    "A02BB8": "Hewlett Packard", "A4 5D 36": "Hewlett Packard",
    "A45D36": "Hewlett Packard", "B4 99 BA": "Hewlett Packard",
    "B499BA": "Hewlett Packard", "B8 AF 67": "Hewlett Packard",
    "B8AF67": "Hewlett Packard", "C8 CB B8": "Hewlett Packard",
    "C8CBB8": "Hewlett Packard", "D0 BF 9C": "Hewlett Packard",
    "D0BF9C": "Hewlett Packard", "D4 85 64": "Hewlett Packard",
    "D48564": "Hewlett Packard", "D8 9D 67": "Hewlett Packard",
    "D89D67": "Hewlett Packard", "DC 4A 3E": "Hewlett Packard",
    "DC4A3E": "Hewlett Packard", "EC 8E B5": "Hewlett Packard",
    "EC8EB5": "Hewlett Packard", "F4 03 43": "Hewlett Packard",
    "F40343": "Hewlett Packard", "FC 15 B4": "Hewlett Packard",
    "FC15B4": "Hewlett Packard",
    "00 1B 78": "Lenovo", "001B78": "Lenovo", "00 21 CC": "Lenovo",
    "0021CC": "Lenovo", "00 26 9E": "Lenovo", "00269E": "Lenovo",
    "08 9E 01": "Lenovo", "089E01": "Lenovo", "10 78 D2": "Lenovo",
    "1078D2": "Lenovo", "1C 39 47": "Lenovo", "1C3947": "Lenovo",
    "20 16 D8": "Lenovo", "2016D8": "Lenovo", "28 D2 44": "Lenovo",
    "3C 91 80": "Lenovo", "3C9180": "Lenovo", "40 1C 83": "Lenovo",
    "401C83": "Lenovo", "44 37 E6": "Lenovo", "4437E6": "Lenovo",
    "48 4D 7E": "Lenovo", "484D7E": "Lenovo", "50 7B 9D": "Lenovo",
    "507B9D": "Lenovo", "54 EE 75": "Lenovo", "54EE75": "Lenovo",
    "60 D9 C7": "Lenovo", "60D9C7": "Lenovo", "68 6A 5A": "Lenovo",
    "686A5A": "Lenovo", "6C 5F 1C": "Lenovo", "6C5F1C": "Lenovo",
    "70 72 0D": "Lenovo", "70720D": "Lenovo", "74 E5 43": "Lenovo",
    "74E543": "Lenovo", "78 DF 9F": "Lenovo", "78DF9F": "Lenovo",
    "80 19 34": "Lenovo", "84 4B F5": "Lenovo", "844BF5": "Lenovo",
    "88 70 8C": "Lenovo", "88708C": "Lenovo", "8C 16 45": "Lenovo",
    "90 4E 2B": "Lenovo", "904E2B": "Lenovo", "98 40 BB": "Lenovo",
    "A0 8C FD": "Lenovo", "A08CFD": "Lenovo", "A4 8C DB": "Lenovo",
    "A48CDB": "Lenovo", "AC E0 10": "Lenovo", "B0 C0 90": "Lenovo",
    "B0C090": "Lenovo", "B8 70 F4": "Lenovo", "B870F4": "Lenovo",
    "C8 5B 76": "Lenovo", "C85B76": "Lenovo", "CC 52 AF": "Lenovo",
    "CC52AF": "Lenovo", "D0 57 7C": "Lenovo", "D8 5D E2": "Lenovo",
    "D85DE2": "Lenovo", "DC 0E A1": "Lenovo", "DC0EA1": "Lenovo",
    "E0 94 67": "Lenovo", "E09467": "Lenovo", "E4 54 E8": "Lenovo",
    "E454E8": "Lenovo", "E8 6A 64": "Lenovo", "E86A64": "Lenovo",
    "EC 89 14": "Lenovo", "EC8914": "Lenovo", "F0 DE F1": "Lenovo",
    "F8 BC 12": "Lenovo", "FC F8 AE": "Lenovo",
    "00 1E 65": "小米生态链", "001E65": "小米生态链",
    "28 6C 07": "小米生态链", "286C07": "小米生态链",
    "78 11 DC": "小米生态链", "F0 B4 29": "小米生态链",
    "34 CE 00": "小米生态链", "50 EC 50": "小米生态链",
    "04 CF 8C": "小米生态链", "64 CC 2E": "小米生态链",
    "8C BEBE": "小米生态链", "9C 99 A0": "小米生态链",
    "A4 C1 38": "小米生态链", "F8 A4 5F": "小米生态链",
    "04 E6 76": "小米生态链", "10 2A B3": "小米生态链",
    "20 47 DA": "小米生态链", "50 64 2B": "小米生态链",
    "7C 49 EB": "小米生态链", "8C DE 52": "小米生态链",
    "9C D2 1E": "小米生态链", "C4 6A B7": "小米生态链",
    "D4 97 0B": "小米生态链", "F0 B4 29": "小米生态链",
    "00 1A 11": "Google", "001A11": "Google", "3C 5A B4": "Google",
    "3C5AB4": "Google", "48 D6 D2": "Google", "48D6D2": "Google",
    "54 60 09": "Google", "546009": "Google", "64 16 66": "Google",
    "641666": "Google", "6C AD F8": "Google", "6CADF8": "Google",
    "94 EB 2D": "Google", "94EB2D": "Google", "A4 77 33": "Google",
    "A47733": "Google", "D8 6C 63": "Google", "D86C63": "Google",
    "F4 F5 D8": "Google", "F4F5D8": "Google", "F4 F5 E8": "Google",
    "F4F5E8": "Google", "1C F2 9A": "Google", "1CF29A": "Google",
    "20 DF B9": "Google", "20DFB9": "Google", "30 FD 38": "Google",
    "30FD38": "Google", "44 07 0B": "Google", "44070B": "Google",
    "F8 8F CA": "Google", "F88FCA": "Google",
    "00 17 88": "Philips", "EC B5 FA": "Philips",
    "00 04 4B": "Xerox", "00044B": "Xerox", "00 00 AA": "Xerox",
    "9C 93 4E": "Xerox", "9C934E": "Xerox",
    "00 0D 93": "Apple", "00 1F F3": "Apple", "00 26 08": "Apple",
    "BC 92 6B": "Apple", "D0 23 DB": "Apple", "F0 DB E2": "Apple",
    "00 09 5B": "NETGEAR", "00 0F B5": "NETGEAR", "00 14 6C": "NETGEAR",
    "00 18 4D": "NETGEAR", "00 1B 2F": "NETGEAR", "00 1E 2A": "NETGEAR",
    "00 22 3F": "NETGEAR", "00 24 B2": "NETGEAR", "00 26 F2": "NETGEAR",
    "20 4E 7F": "NETGEAR", "20 E5 2A": "NETGEAR", "28 C6 8E": "NETGEAR",
    "2C 30 33": "NETGEAR", "30 46 9A": "NETGEAR", "38 94 ED": "NETGEAR",
    "3C 37 86": "NETGEAR", "40 5D 82": "NETGEAR", "44 94 4A": "NETGEAR",
    "4C 60 DE": "NETGEAR", "9C 3D CF": "NETGEAR", "A0 04 60": "NETGEAR",
    "A0 40 A0": "NETGEAR", "B0 39 56": "NETGEAR", "B0 7F B9": "NETGEAR",
    "C0 3F 0E": "NETGEAR", "C4 3D C7": "NETGEAR", "CC 40 D0": "NETGEAR",
    "E0 46 9A": "NETGEAR", "E0 91 F5": "NETGEAR", "E4 F4 C6": "NETGEAR",
    "E8 FC AF": "NETGEAR", "F8 73 94": "NETGEAR",
    "00 0E 58": "Sonos", "000E58": "Sonos", "5C AA FD": "Sonos",
    "5CAAFD": "Sonos", "78 28 CA": "Sonos", "7828CA": "Sonos",
    "94 9F 3E": "Sonos", "949F3E": "Sonos", "B8 E9 37": "Sonos",
    "B8E937": "Sonos", "48 A6 B8": "Sonos", "48A6B8": "Sonos",
    "00 1C 2A": "Amped Wireless", "001C2A": "Amped Wireless",
    "00 13 10": "Cisco-Linksys", "001310": "Cisco-Linksys",
    "00 18 F8": "Cisco-Linksys", "0018F8": "Cisco-Linksys",
    "00 1A 70": "Cisco-Linksys", "00 1C 10": "Cisco-Linksys",
    "00 1D 7E": "Cisco-Linksys", "001D7E": "Cisco-Linksys",
    "00 1E E5": "Cisco-Linksys", "001EE5": "Cisco-Linksys",
    "00 21 29": "Cisco-Linksys", "00 22 6B": "Cisco-Linksys",
    "00226B": "Cisco-Linksys", "00 23 69": "Cisco-Linksys",
    "00 25 9C": "Cisco-Linksys", "20 AA 4B": "Cisco-Linksys",
    "20AA4B": "Cisco-Linksys", "48 F8 B3": "Cisco-Linksys",
    "58 6D 8F": "Cisco-Linksys", "586D8F": "Cisco-Linksys",
    "68 7F 74": "Cisco-Linksys", "687F74": "Cisco-Linksys",
    "C0 C1 C0": "Cisco-Linksys", "C0C1C0": "Cisco-Linksys",
    "E8 9F 80": "Cisco-Linksys", "E89F80": "Cisco-Linksys",
    "00 1F 90": "Actiontec", "001F90": "Actiontec", "00 26 B8": "Actiontec",
    "0026B8": "Actiontec", "40 5F C2": "Actiontec", "405FC2": "Actiontec",
    "00 1C DF": "Belkin", "001CDF": "Belkin", "00 22 75": "Belkin",
    "002275": "Belkin", "08 86 3B": "Belkin", "08863B": "Belkin",
    "94 10 3E": "Belkin", "94103E": "Belkin", "B4 75 0E": "Belkin",
    "B4750E": "Belkin", "C0 56 27": "Belkin", "C05627": "Belkin",
    "EC 1A 59": "Belkin", "EC1A59": "Belkin",
    "00 1D D3": "合勤 Zyxel", "001DD3": "合勤 Zyxel", "00 13 49": "合勤 Zyxel",
    "001349": "合勤 Zyxel", "5C F4 AB": "合勤 Zyxel", "5CF4AB": "合勤 Zyxel",
    "B0 B2 DC": "合勤 Zyxel", "B0B2DC": "合勤 Zyxel",
    "00 1B FC": "ASUSTek", "001BFC": "ASUSTek",
    "00 0C 43": "MediaTek", "000C43": "MediaTek", "00 0E 8E": "MediaTek",
    "000E8E": "MediaTek", "1C 4B D6": "MediaTek", "1C4BD6": "MediaTek",
    "00 0C E7": "MediaTek", "000CE7": "MediaTek",
    "00 26 5E": "海康威视", "00265E": "海康威视", "04 02 1F": "海康威视",
    "44 19 B6": "海康威视", "48 EA 63": "海康威视", "48EA63": "海康威视",
    "4C BD 8F": "海康威视", "4CBD8F": "海康威视", "54 C4 15": "海康威视",
    "58 03 FB": "海康威视", "5803FB": "海康威视", "5C 16 7D": "海康威视",
    "5C167D": "海康威视", "68 6D BC": "海康威视", "686DBC": "海康威视",
    "8C E7 48": "海康威视", "8CE748": "海康威视", "94 E1 AC": "海康威视",
    "94E1AC": "海康威视", "A4 14 37": "海康威视", "A41437": "海康威视",
    "AC B9 2F": "海康威视", "ACB92F": "海康威视", "B4 A3 82": "海康威视",
    "B4A382": "海康威视", "BC AD 28": "海康威视", "BCAD28": "海康威视",
    "C0 56 E3": "海康威视", "C056E3": "海康威视", "C4 2F 90": "海康威视",
    "C42F90": "海康威视", "D4 83 04": "海康威视", "D48304": "海康威视",
    "E0 CA 3C": "海康威视", "E0CA3C": "海康威视", "F8 4D FC": "海康威视",
    "F84DFC": "海康威视",
    "00 12 12": "大华", "001212": "大华", "00 1C C4": "大华",
    "001CC4": "大华", "14 49 78": "大华", "144978": "大华",
    "34 68 0D": "大华", "34680D": "大华", "3C EF 8C": "大华",
    "3CEF8C": "大华", "4C 11 BF": "大华", "4C11BF": "大华",
    "64 46 4B": "大华", "64464B": "大华", "6C 1C 71": "大华",
    "6C1C71": "大华", "90 02 A9": "大华", "9C 14 63": "大华",
    "9C1463": "大华", "A0 66 36": "大华", "A06636": "大华",
    "B4 47 5E": "大华", "B4475E": "大华", "BC 32 5F": "大华",
    "BC325F": "大华", "C0 6D ED": "大华", "C06DED": "大华",
    "C4 6E 1F": "大华", "D4 43 0A": "大华", "D4430A": "大华",
    "E0 50 8B": "大华", "E0508B": "大华", "EC 5F 62": "大华",
    "EC5F62": "大华",
    "00 04 4D": "Cisco", "00 09 43": "Cisco", "00 0A 41": "Cisco",
    "00 0A 42": "Cisco", "00 0B 46": "Cisco", "00 0B 5F": "Cisco",
    "00 0B BE": "Cisco", "00 0C 30": "Cisco", "00 0C 31": "Cisco",
    "00 0C 85": "Cisco", "00 0C CE": "Cisco", "00 0D 28": "Cisco",
    "00 0D 29": "Cisco", "00 0D BC": "Cisco", "00 0D EC": "Cisco",
    "00 0E 38": "Cisco", "00 0E 39": "Cisco", "00 0E 83": "Cisco",
    "00 0E 84": "Cisco", "00 0E D6": "Cisco", "00 0E D7": "Cisco",
    "00 0F 23": "Cisco", "00 0F 24": "Cisco", "00 0F 34": "Cisco",
    "00 0F 35": "Cisco", "00 0F 8F": "Cisco", "00 0F 90": "Cisco",
    "00 10 07": "Cisco", "00 10 0B": "Cisco", "00 10 0D": "Cisco",
    "00 10 14": "Cisco", "00 10 1F": "Cisco", "00 10 29": "Cisco",
    "00 10 2F": "Cisco", "00 10 54": "Cisco", "00 10 79": "Cisco",
    "00 10 7B": "Cisco", "00 10 A6": "Cisco", "00 10 F6": "Cisco",
    "00 11 20": "Cisco", "00 11 21": "Cisco", "00 11 5C": "Cisco",
    "00 11 92": "Cisco", "00 11 93": "Cisco", "00 11 BB": "Cisco",
    "00 11 BC": "Cisco", "00 12 00": "Cisco", "00 12 01": "Cisco",
    "00 12 43": "Cisco", "00 12 44": "Cisco", "00 12 7F": "Cisco",
    "00 12 80": "Cisco", "00 12 D9": "Cisco", "00 12 DA": "Cisco",
    "00 13 19": "Cisco", "00 13 1A": "Cisco", "00 13 5F": "Cisco",
    "00 13 60": "Cisco", "00 13 7F": "Cisco", "00 13 80": "Cisco",
    "00 13 C3": "Cisco", "00 13 C4": "Cisco", "00 14 1B": "Cisco",
    "00 14 1C": "Cisco", "00 14 69": "Cisco", "00 14 6A": "Cisco",
    "00 14 A8": "Cisco", "00 14 A9": "Cisco", "00 14 F1": "Cisco",
    "00 14 F2": "Cisco", "00 15 2B": "Cisco", "00 15 2C": "Cisco",
    "00 15 62": "Cisco", "00 15 63": "Cisco", "00 15 C6": "Cisco",
    "00 15 C7": "Cisco", "00 15 F9": "Cisco", "00 15 FA": "Cisco",
    "00 16 46": "Cisco", "00 16 47": "Cisco", "00 16 9C": "Cisco",
    "00 16 9D": "Cisco", "00 16 C7": "Cisco", "00 16 C8": "Cisco",
    "00 17 0E": "Cisco", "00 17 0F": "Cisco", "00 17 5A": "Cisco",
    "00 17 94": "Cisco", "00 17 95": "Cisco", "00 17 DF": "Cisco",
    "00 17 E0": "Cisco", "00 18 18": "Cisco", "00 18 19": "Cisco",
    "00 18 73": "Cisco", "00 18 74": "Cisco", "00 18 B9": "Cisco",
    "00 18 BA": "Cisco", "00 19 06": "Cisco", "00 19 07": "Cisco",
    "00 19 2F": "Cisco", "00 19 30": "Cisco", "00 19 55": "Cisco",
    "00 19 56": "Cisco", "00 19 A9": "Cisco", "00 19 AA": "Cisco",
    "00 19 E7": "Cisco", "00 19 E8": "Cisco", "00 1A 2F": "Cisco",
    "00 1A 30": "Cisco", "00 1A 6C": "Cisco", "00 1A 6D": "Cisco",
    "00 1A A1": "Cisco", "00 1A A2": "Cisco", "00 1A E2": "Cisco",
    "00 1A E3": "Cisco", "00 1B 0C": "Cisco", "00 1B 0D": "Cisco",
    "00 1B 2A": "Cisco", "00 1B 2B": "Cisco", "00 1B 53": "Cisco",
    "00 1B 54": "Cisco", "00 1B 8F": "Cisco", "00 1B 90": "Cisco",
    "00 1B D4": "Cisco", "00 1B D5": "Cisco", "00 1C 0E": "Cisco",
    "00 1C 0F": "Cisco", "00 1C 57": "Cisco", "00 1C 58": "Cisco",
    "00 1C B0": "Cisco", "00 1C B1": "Cisco", "00 1C F6": "Cisco",
    "00 1C F9": "Cisco", "00 1D 45": "Cisco", "00 1D 46": "Cisco",
    "00 1D 70": "Cisco", "00 1D 71": "Cisco", "00 1D A1": "Cisco",
    "00 1D A2": "Cisco", "00 1D E5": "Cisco", "00 1D E6": "Cisco",
    "00 1E 13": "Cisco", "00 1E 14": "Cisco", "00 1E 49": "Cisco",
    "00 1E 4A": "Cisco", "00 1E 79": "Cisco", "00 1E 7A": "Cisco",
    "00 1E BD": "Cisco", "00 1E BE": "Cisco", "00 1E F6": "Cisco",
    "00 1E F7": "Cisco", "00 1F 26": "Cisco", "00 1F 27": "Cisco",
    "00 1F 6C": "Cisco", "00 1F 6D": "Cisco", "00 1F 9D": "Cisco",
    "00 1F 9E": "Cisco", "00 1F C9": "Cisco", "00 1F CA": "Cisco",
    "00 20 00": "Cisco", "00 21 1B": "Cisco", "00 21 1C": "Cisco",
    "00 21 55": "Cisco", "00 21 56": "Cisco", "00 21 A0": "Cisco",
    "00 21 A1": "Cisco", "00 21 D7": "Cisco", "00 21 D8": "Cisco",
    "00 22 0C": "Cisco", "00 22 0D": "Cisco", "00 22 55": "Cisco",
    "00 22 56": "Cisco", "00 22 90": "Cisco", "00 22 91": "Cisco",
    "00 22 BD": "Cisco", "00 22 BE": "Cisco", "00 23 04": "Cisco",
    "00 23 05": "Cisco", "00 23 33": "Cisco", "00 23 34": "Cisco",
    "00 23 5D": "Cisco", "00 23 5E": "Cisco", "00 23 9C": "Cisco",
    "00 23 9D": "Cisco", "00 23 EA": "Cisco", "00 23 EB": "Cisco",
    "00 24 13": "Cisco", "00 24 14": "Cisco", "00 24 50": "Cisco",
    "00 24 51": "Cisco", "00 24 97": "Cisco", "00 24 98": "Cisco",
    "00 24 C4": "Cisco", "00 24 C5": "Cisco", "00 24 F7": "Cisco",
    "00 24 F9": "Cisco", "00 25 45": "Cisco", "00 25 46": "Cisco",
    "00 25 84": "Cisco", "00 25 85": "Cisco", "00 25 B4": "Cisco",
    "00 25 B5": "Cisco", "00 25 9C": "Cisco", "00 26 0A": "Cisco",
    "00 26 0B": "Cisco", "00 26 51": "Cisco", "00 26 52": "Cisco",
    "00 26 98": "Cisco", "00 26 99": "Cisco", "00 26 CA": "Cisco",
    "00 26 CB": "Cisco", "00 27 0C": "Cisco", "00 27 0D": "Cisco",
    "00 27 21": "Cisco", "00 27 22": "Cisco",
    "00 1A 8C": "3Com", "001A8C": "3Com", "00 50 04": "3Com",
    "005004": "3Com", "00 60 08": "3Com", "006008": "3Com",
    "00 60 97": "3Com", "006097": "3Com",
    # 群晖 Synology / 威联通 QNAP
    "001132": "Synology", "9009D0": "Synology", "245EBE": "QNAP",
    # Ubiquiti
    "24A43C": "Ubiquiti", "0418D6": "Ubiquiti", "F09FC2": "Ubiquiti",
    "788A20": "Ubiquiti", "68D79A": "Ubiquiti", "74ACB9": "Ubiquiti",
    "802AA8": "Ubiquiti", "DC9F22": "Ubiquiti", "E063DA": "Ubiquiti",
    "687251": "Ubiquiti", "B4FBE4": "Ubiquiti", "FCEEC2": "Ubiquiti",
    "9C05D6": "Ubiquiti", "44D9E7": "Ubiquiti",
    # MikroTik
    "4C5E0C": "MikroTik", "6C3B6B": "MikroTik", "744D28": "MikroTik",
    "18FD74": "MikroTik", "48A98A": "MikroTik", "785EA2": "MikroTik",
    "DC2C6E": "MikroTik", "E48D8C": "MikroTik",
    # Aruba
    "000B86": "Aruba", "204C03": "Aruba", "6CF37F": "Aruba", "84D47E": "Aruba",
    "9C1C12": "Aruba", "B4B686": "Aruba", "D8C7C8": "Aruba", "186472": "Aruba",
    # Ruckus
    "001392": "Ruckus", "002482": "Ruckus", "24C9A1": "Ruckus", "2C5D93": "Ruckus",
    "50A733": "Ruckus", "6CAA00": "Ruckus", "8C0C90": "Ruckus", "C0C520": "Ruckus",
    # Amazon（Echo / Fire TV / Ring）
    "44650D": "Amazon", "6854FD": "Amazon", "74C246": "Amazon", "84D6D0": "Amazon",
    "A002DC": "Amazon", "AC63BE": "Amazon", "F0272D": "Amazon", "0C47C9": "Amazon",
    "6837E9": "Amazon", "78E103": "Amazon", "40B4CD": "Amazon", "4CEFC0": "Amazon",
    # 智能家居
    "10D561": "Tuya", "780F77": "Broadlink", "54EF44": "Aqara",
    # D-Link
    "00055D": "D-Link", "000D88": "D-Link", "000F3D": "D-Link", "001195": "D-Link",
    "001346": "D-Link", "0015E9": "D-Link", "00179A": "D-Link", "00195B": "D-Link",
    "001B11": "D-Link", "001CF0": "D-Link", "001E58": "D-Link", "002191": "D-Link",
    "0022B0": "D-Link", "002401": "D-Link", "00265A": "D-Link", "0050BA": "D-Link",
    "1CAFF7": "D-Link", "5CD998": "D-Link", "78542E": "D-Link", "84C9B2": "D-Link",
    "B8A386": "D-Link", "C8BE19": "D-Link", "F07D68": "D-Link", "FC7516": "D-Link",
    # 腾达 / 中兴 / 新华三 / 锐捷
    "C83A35": "Tenda", "D8320E": "Tenda", "081078": "Tenda",
    "0019C6": "ZTE", "001A2A": "ZTE", "0026ED": "ZTE", "34E0CF": "ZTE",
    "4C09B4": "ZTE", "CC1AFA": "ZTE", "DC028E": "ZTE",
    "002389": "H3C", "3C8C40": "H3C", "70F96D": "H3C",
    "00749C": "锐捷 Ruijie", "300D9E": "锐捷 Ruijie", "885A92": "锐捷 Ruijie",
}

# 前缀 -> 设备类型推断用的关键词
VENDOR_KIND_HINTS = [
    ("apple", "手机 / 电脑"),
    ("samsung", "手机 / 家电"),
    ("xiaomi", "手机 / 智能家居"),
    ("华为", "手机 / 网络设备"),
    ("huawei", "手机 / 网络设备"),
    ("honor", "手机"),
    ("oppo", "手机"), ("vivo", "手机"), ("oneplus", "手机"),
    ("tp-link", "路由器 / AP"),
    ("netgear", "路由器 / AP"),
    ("buffalo", "路由器 / NAS"),
    ("zyxel", "路由器 / AP"),
    ("cisco", "交换机 / AP"),
    ("linksys", "路由器"),
    ("belkin", "路由器"),
    ("ubiquiti", "AP / 交换机"),
    ("aruba", "AP"),
    ("ruckus", "AP"),
    ("mikrotik", "路由器"),
    ("synology", "NAS"),
    ("qnap", "NAS"),
    ("ikua", "路由器 / 网关"),
    ("mellanox", "服务器 / 高速网卡"),
    ("imilab", "智能摄像头"),
    ("ai-link", "物联网模块"),
    ("liteon", "网通模块"),
    ("d-link", "路由器 / AP"),
    ("dlink", "路由器 / AP"),
    ("tenda", "路由器 / AP"),
    ("zte", "路由器 / 光猫"),
    ("h3c", "交换机 / AP"),
    ("ruijie", "交换机 / AP"),
    ("锐捷", "交换机 / AP"),
    ("amazon", "智能音箱 / 电视棒"),
    ("tuya", "智能家居"),
    ("broadlink", "红外 / 智能家居网关"),
    ("aqara", "智能家居"),
    ("yeelight", "智能灯"),
    ("espressif", "物联网模块"),
    ("raspberry", "树莓派"),
    ("signify", "智能灯"),
    ("philips", "智能灯"),
    ("sonos", "智能音箱"),
    ("google", "智能音箱 / 手机"),
    ("nintendo", "游戏机"),
    ("sony", "游戏机 / 电视"),
    ("海康", "网络摄像头 / NVR"),
    ("大华", "网络摄像头 / NVR"),
    ("brother", "打印机"),
    ("epson", "打印机"),
    ("xerox", "打印机"),
    ("hewlett", "打印机 / 电脑"),
    ("intel", "电脑"),
    ("dell", "电脑 / 服务器"),
    ("lenovo", "电脑"),
    ("asustek", "电脑 / 路由器"),
    ("micro", "电脑"),
    ("vmware", "虚拟机"),
    ("virtualbox", "虚拟机"),
    ("hyper-v", "虚拟机"),
    ("docker", "容器网卡"),
    ("qemu", "虚拟机"),
    ("realtek", "网卡"),
    ("azurewave", "无线模块"),
    ("mediatek", "无线模块"),
]


def _sanitize(table: dict[str, str]) -> dict[str, str]:
    """清理键：去掉非十六进制字符，只保留 6 位前缀。

    这样表里写成 "00 1A 2F" / "0c:8b:fd" 之类的写法也能被正确识别。
    """
    out: dict[str, str] = {}
    for key, value in table.items():
        clean = "".join(c for c in key if c in "0123456789abcdefABCDEF").upper()
        if len(clean) >= 6:
            out[clean[:6]] = value
    return out


def normalize(mac: str) -> str:
    """把 MAC 统一成 12 位大写十六进制，失败返回空串。

    兼容 macOS ``arp`` 省略前导零的写法（``8:9b:4b:15:e8:54``）、
    ``AA-BB-CC-DD-EE-FF``、Cisco 的 ``0011.2233.4455`` 和纯十六进制串。
    """
    text = (mac or "").strip().lower()
    if not text or "incomplete" in text:
        return ""
    if ":" in text or "-" in text:
        parts = re.split(r"[:\-]", text)
        if len(parts) == 6 and all(part and len(part) <= 2 for part in parts):
            if all(all(c in "0123456789abcdef" for c in part) for part in parts):
                return "".join(part.zfill(2) for part in parts).upper()
    hex_only = "".join(c for c in text if c in "0123456789abcdef")
    if len(hex_only) < 12:
        return ""
    return hex_only[:12].upper()


def oui_csv_candidates() -> list[str]:
    """oui.csv 的查找顺序：环境变量 → 项目目录 → data/ 目录。

    容器部署时项目目录是只读的镜像层，把表放进被挂载的 data/ 才能持久化。
    """
    base = os.path.dirname(os.path.abspath(__file__))
    paths = []
    env = os.environ.get("LAN_SCAN_OUI")
    if env:
        paths.append(env)
    paths.append(os.path.join(base, "oui.csv"))
    paths.append(os.path.join(base, "data", "oui.csv"))
    return paths


def _load_external_table() -> dict[str, str]:
    table: dict[str, str] = {}
    for path in oui_csv_candidates():
        if not os.path.isfile(path):
            continue
        try:
            with open(path, newline="", encoding="utf-8", errors="replace") as fh:
                reader = csv.reader(fh)
                next(reader, None)
                for row in reader:
                    if len(row) < 3:
                        continue
                    assignment = (row[1] or "").strip().upper()
                    org = (row[2] or "").strip()
                    if len(assignment) >= 6 and org and assignment[:6] not in table:
                        table[assignment[:6]] = org
        except Exception:
            continue
    return table


_TABLE: dict[str, str] = {}
_ORG_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "ltd", "limited", "llc",
    "gmbh", "mbh", "sa", "sas", "bv", "nv", "ag", "oy", "ab", "as", "spa", "plc",
    "pty", "pte", "sarl", "srl", "kk", "kg", "company", "technologies", "technology",
    "tech", "electronics", "electronic", "communications", "communication",
    "networks", "network", "systems", "system", "group", "holding", "holdings",
    "international", "intl", "sdn", "bhd", "sro", "doo", "zrt", "kft",
    "computer", "computers", "software", "mobile", "telecom", "telecommunication",
    "telecommunications", "semiconductor", "semiconductors", "optical",
    "enterprise", "solutions", "service", "services", "digital", "information",
    "industry", "industrial", "coltd", "col",
}
_ORG_TAIL_RE = re.compile(r"[,\s]+([A-Za-z][A-Za-z.]{1,14})\.?$")


def clean_org(name: str) -> str:
    """把 "Apple, Inc." 整理成 "Apple"，"Xiaomi Communications Co Ltd" 变成
    "Xiaomi Communications"。只是让界面好读，不影响匹配。"""
    text = (name or "").strip().strip('"')
    original = text
    for _ in range(5):
        match = _ORG_TAIL_RE.search(text)
        if not match:
            break
        token = match.group(1).lower().replace(".", "")
        head = text[: match.start()].strip()
        if token in _ORG_SUFFIXES and len(head) >= 4:
            text = head
        else:
            break
    return text or original


def _build_table() -> dict[str, str]:
    """内置表优先（名字短好读），oui.csv 补充其余厂商。"""
    table = {key: clean_org(value) for key, value in _load_external_table().items()}
    table.update(_sanitize(BUILTIN))
    return table


_TABLE = _build_table()


def lookup(mac: str) -> str:
    """按 OUI 返回厂商名，查不到返回"未知厂商"。"""
    key = normalize(mac)
    if not key:
        return "未知厂商"
    for length in (6, 7):
        vendor = _TABLE.get(key[:length])
        if vendor:
            return vendor
    # 本地管理位（随机的私有 MAC）
    try:
        first_octet = int(key[:2], 16)
        if first_octet & 0x02:
            return "私有/随机 MAC"
    except ValueError:
        pass
    return "未知厂商"


# mDNS 服务类型 → 设备类型
SERVICE_KIND_HINTS = [
    ("companion-link", "Apple 设备"),
    ("device-info", "Apple 设备"),
    ("rdlink", "Apple 设备"),
    ("airplay", "AirPlay 设备"),
    ("raop", "AirPlay 音箱"),
    ("googlecast", "Chromecast / 投屏设备"),
    ("spotify", "智能音箱"),
    ("sonos", "智能音箱"),
    ("amzn", "Amazon 智能设备"),
    ("homekit", "HomeKit 配件"),
    ("hap", "HomeKit 配件"),
    ("esphomelib", "ESP 物联网设备"),
    ("shelly", "智能开关"),
    ("octoprint", "3D 打印机"),
    ("arduino", "Arduino 设备"),
    ("mqtt", "MQTT 物联网设备"),
    ("ipp", "打印机"),
    ("printer", "打印机"),
    ("scanner", "扫描仪"),
    ("afpovertcp", "NAS / Mac"),
    ("nfs", "NAS / 文件服务器"),
    ("smb", "文件共享设备"),
    ("workstation", "电脑"),
    ("daap", "媒体库"),
    ("rfb", "VNC 远程桌面主机"),
    ("sftp-ssh", "Linux 主机"),
    ("ssh", "Linux 主机"),
    ("telnet", "网络设备"),
    ("privet", "Google 云打印"),
    ("http", "Web 服务设备"),
    ("https", "Web 服务设备"),
]


def infer_kind(vendor: str = "", hostname: str = "", ports: list[int] | None = None,
               services: list[str] | None = None) -> str:
    """推断设备类型。

    判断顺序（越靠前越可信）：
    强特征端口 → 端口组合 → 主机名关键词 → mDNS 服务 → 厂商 → 弱端口特征。
    这样 NAS 不会被 554 端口误判成摄像头，MacBook 也不会因为开了 AirPlay
    被当成 Apple TV。
    """
    port_set = set(ports or [])
    host = (hostname or "").lower()
    vendor_l = (vendor or "").lower()
    service_text = " ".join(services or []).lower()

    # 1) 强特征端口：出现即基本可以定性
    for needles, kind in (
        ({62078}, "iPhone / iPad"),
        ({9100, 515, 631}, "打印机"),
        ({37777}, "网络摄像头 / NVR"),
        ({32400}, "媒体服务器 (Plex)"),
        ({8123}, "智能家居中枢 (Home Assistant)"),
        ({548, 2049}, "NAS / 文件服务器"),
        ({3389}, "Windows 远程桌面主机"),
        ({5060}, "VoIP 电话 / 网关"),
    ):
        if port_set & needles:
            return kind

    # 2) 主机名关键词（设备名往往直说了它是什么）
    for keyword, kind in (
        ("macbook", "电脑"), ("mac mini", "电脑"), ("mac-mini", "电脑"),
        ("mac pro", "电脑"), ("imac", "电脑"), ("iphone", "手机"),
        ("ipad", "平板"), ("android", "手机"), ("pixel", "手机"),
        ("desktop", "电脑"), ("laptop", "电脑"), ("notebook", "电脑"),
        ("pc-", "电脑"), ("thinkpad", "电脑"), ("raspberry", "树莓派"),
        ("homeassistant", "智能家居中枢"), ("hass", "智能家居中枢"),
        ("nas", "NAS / 文件服务器"), ("storage", "NAS / 文件服务器"),
        ("router", "路由器 / 网关"), ("gateway", "路由器 / 网关"),
        ("openwrt", "路由器 / 网关"), ("ikuai", "路由器 / 网关"),
        ("repeater", "无线中继"), ("extender", "无线中继"),
        ("ap-", "无线 AP"), ("accesspoint", "无线 AP"),
        ("printer", "打印机"), ("print", "打印机"),
        ("cam", "网络摄像头"), ("doorbell", "智能门铃"),
        ("speaker", "智能音箱"), ("homepod", "智能音箱"),
        ("echo", "智能音箱"), ("soundbar", "音箱"),
        ("chromecast", "Chromecast / 投屏设备"), ("appletv", "Apple TV"),
        ("apple-tv", "Apple TV"), ("tv-", "电视 / 盒子"), ("-tv", "电视 / 盒子"),
        ("xbox", "游戏机"), ("playstation", "游戏机"),
        ("deng", "智能灯"), ("lamp", "智能灯"), ("light", "智能灯"),
        ("bulb", "智能灯"), ("strip", "智能灯带"),
        ("plug", "智能插座"), ("switch-", "智能开关"), ("socket", "智能插座"),
        ("sensor", "传感器"), ("thermo", "温控设备"),
        ("phone", "手机"), ("tablet", "平板"), ("watch", "智能手表"),
        ("server", "服务器"), ("ubuntu", "Linux 主机"), ("debian", "Linux 主机"),
        ("centos", "Linux 主机"), ("esxi", "虚拟化主机"),
    ):
        if keyword in host:
            return kind

    # 3) 端口组合
    is_nas = bool({5000, 5001} <= port_set) or (2049 in port_set and 111 in port_set)
    if is_nas:
        return "NAS / 文件服务器"
    for needles, kind in (
        ({8008, 8009}, "Chromecast / 投屏设备"),
        ({7000}, "AirPlay 设备"),
        ({5900}, "VNC 远程桌面主机"),
        ({1883}, "MQTT 物联网设备"),
        ({5555}, "Android 设备"),
        ({5357}, "Windows 电脑"),
    ):
        if port_set & needles:
            return kind
    if 53 in port_set and port_set & {80, 443, 8080} and port_set & {22, 23, 8291}:
        return "路由器 / 网关"
    if 554 in port_set or (8000 in port_set and "cam" in host):
        return "网络摄像头"
    if 53 in port_set:
        return "DNS / 路由器"


    # 4) mDNS 服务（设备自己广播的服务类型很有说服力）
    for keyword, kind in SERVICE_KIND_HINTS:
        if keyword in service_text:
            return kind

    # 5) 厂商
    for keyword, kind in VENDOR_KIND_HINTS:
        if keyword in vendor_l:
            return kind

    # 6) 弱端口特征兜底
    if 22 in port_set and port_set & {80, 443, 8080, 8081, 8443}:
        return "Linux 服务器"
    if port_set & {80, 443, 8080, 8081, 8443, 8000}:
        return "Web 服务设备"
    if 22 in port_set:
        return "Linux 主机 (SSH)"
    if 445 in port_set or 139 in port_set:
        return "文件共享设备"
    if 49152 in port_set or 49153 in port_set:
        return "UPnP 设备"

    return "未知设备"


# 兼容旧名字
def guess_kind(vendor: str, hostname: str = "", ports: list[int] | None = None) -> str:
    return infer_kind(vendor, hostname, ports, [])


