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

 _init contains raw text date that maps to init field in the user table
contacts contains an array of json objects that match with the contact table
diary contains a json object, this contains keys that are a date and adherence and sideeffects and notes objects within each date. there is an adherance table and a side_effect and note tables that match these fields and also contain a date that should be taken from the key.
favourites match onto the favourite collection
meta contains one key 21dayoption that matches the meta table containing a field twenty_one_day_option
plans matches the plan collection
profilers matches profiler
reminders matches reminder. they keys are used to match to the 'type' field of each entry and the contents of each json object matches the fields within the sub-objects
thoughts matches thought collection. this contains a json object. each key matches to the path field, and there is a list of json objects for each path that map onto the negative and positive fields. There might be multiple db entries for each path.
goals matches goal collection and contains an array of json objects, each of which match onto the collection fields.
use the test user identified in the code, but also do it for the user whose SweetID is k.court.
integrate the above and add the data into strapi, logging any issues or data that you don't know how to handle so I can improve the script

todo monday: run script again after clearning db, then run with k.court in staging to check goals and thoughts

user data import:

1. test things work with import-test-user
2. run on all users with import_all_users
3. check import_errors and resolve any issues
4. test works with test_userdata_mapping.py. I did this once with the production and once with staging (where you can use Kate's data, saved under the username k.court)

