# current issues 5/8/26

* Home: has the correct subsections, but there is no description for each subsection, and no distinction between different types of menu item (this has hopefully been fixed)
* Incorrect ordering of menu items
* Incorrect titles, they need to come from structure.json (new v should address this by looking in structure.json)

When inserting link in markdown to a video, need to use the copy url button to find the name, rather than the file name

========================================
🎯 UNIQUE ROLES FOUND IN users.json
========================================

 • Role: 'staff' (Found in 7 user records)
 • Role: 'sysadmin' (Found in 3 user records)
 • Role: 'user' (Found in 1072 user records)

 


content import:
1. import_all_to_strapi.py
Do not run this again - use a dump file exported from Kate's local copy as this is correct. 

user data import:

1. test things work with import-test-user (check mobile number as I missed this first pass)
2. run on all users with import_all_users
3. check import_errors and resolve any issues
4. test works with test_userdata_mapping.py I did this once with the production and once with staging (where you can use Kate's data, saved under the username k.court)
5. run for all with imprt_all_userdata.py
6. check errors in import_user_content_errors.json
7. use exportUserRolesToCSV to identify the roles of various users so can add those with staff role to the admin UI.
Production emails to be added as admins:
sarah-jane.stewart@ucl.ac.uk
sue.thompson@ncl.ac.uk
lmcgeagh@brookes.ac.uk
kate.court@ncl.ac.uk
raegan.barrows@warwick.ac.uk
kiran.thomas@nhs.net
M.L.Dalby@warwick.ac.uk

8. add registration codes to the collection, import_registration_codes.py

Staging emails to be added as admins:


❌ User with SweetID 'A0002' was not found in Strapi. Skipping userdata.


where are contact preferences stored in the data? The above script doesn't include them





import from prod to staging: all pages and component tables, messages table. 