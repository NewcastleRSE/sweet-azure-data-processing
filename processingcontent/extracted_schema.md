Table: [ contacts ] - change to contact
  └── Foreign Key: user_id (FK -> users.id)
  └── Detected Columns:
      • type                      (Types seen: str)
      • name                      (Types seen: str)
      • phone                     (Types seen: str)
      • email                     (Types seen: str)

 Table: [ diary ]
  └── Foreign Key: user_id (FK -> users.id)
  └── Detected Columns:
      • 2022-07-22                (Types seen: dict)
      • 2022-07-21                (Types seen: dict)
      • 2023-11-02                (Types seen: dict)
      • 2022-03-21                (Types seen: dict) 

      etc.

      Note: This data will need manipulating so that actual date isn't the key.


 Table / Blob Type: [ diary ]
 ----------------------------------------------------------------------
  📍 Location Path: {DATE}
      └── • [Type]                       (Types: dict (nested object))
      └── • adherence                    (Types: bool)
  📍 Location Path: {DATE}.drugs
      └── • [Type]                       (Types: dict (nested object))
      └── • date                         (Types: str)
      └── • drug                         (Types: str)
  📍 Location Path: {DATE}.drugs.taken
      └── • [Type]                       (Types: dict (nested object))
      └── • date                         (Types: str)
      └── • time                         (Types: str)
  📍 Location Path: {DATE}.sideeffects
      └── • [Type]                       (Types: list (array))
  📍 Location Path: {DATE}.sideeffects[]
      └── • type                         (Types: str)
      └── • description                  (Types: str)
      └── • date                         (Types: str)
      └── • frequency                    (Types: str)
      └── • severity                     (Types: str)
      └── • impact                       (Types: str)
      └── • notes                        (Types: str)

Table: [ fillins ] - not in use?
  └── Foreign Key: user_id (FK -> users.id)
  └── Detected Columns:

 Table: [ goals ] change to goal
  └── Foreign Key: user_id (FK -> users.id)
  └── Detected Columns:
      • goaltype                  (Types seen: str)
      • status                    (Types seen: str) - protected name, use state instead
      • reviewDate                (Types seen: str)
      • detail                    (Types seen: str)
      • days                      (Types seen: str)
      • minutes                   (Types seen: str)
      • outcome                   (Types seen: str)

 Table: [ meta ]
  └── Foreign Key: user_id (FK -> users.id)
  └── Detected Columns:
      • 21dayoption               (Types seen: int) twenty_one_day_option
      • goalmsg                   (Types seen: dict) check

  📍 Location Path: goalmsg
      └── • [Type]                       (Types: dict (nested object))
  📍 Location Path: goalmsg.activity
      └── • [Type]                       (Types: dict (nested object))
      └── • y                            (Types: int)
      └── • p                            (Types: int)
      └── • n                            (Types: int)
  📍 Location Path: goalmsg.eating
      └── • [Type]                       (Types: dict (nested object))
      └── • y                            (Types: int)
      └── • p                            (Types: int)
      └── • n                            (Types: int)
  📍 Location Path: root
      └── • 21dayoption                  (Types: int)

 Table: [ plans ]
  └── Foreign Key: user_id (FK -> users.id)
  └── Detected Columns:
      • taking-ht                 (Types seen: dict) check

        📍 Location Path: taking-ht
      └── • [Type]                       (Types: dict (nested object))
      └── • type                         (Types: str)
      └── • time                         (Types: str)
      └── • place                        (Types: str)
      └── • activity                     (Types: str)
      └── • plan                         (Types: str)

 Table: [ profilers ] change to profiler
  └── Foreign Key: user_id (FK -> users.id)
  └── Detected Columns:
      • dueDate                   (Types seen: str)
      • dateComplete              (Types seen: str)
      • result                    (Types seen: str)
      • concernAreas              (Types seen: str)
      • concernSpecifics          (Types seen: list) check
      • reminderDate              (Types seen: str)
      • reason                    (Types seen: str)

        📍 Location Path: concernSpecifics
      └── • [Type]                       (Types: list (array))
  📍 Location Path: concernSpecifics[]
      └── • [Primitive Array Values]     (Types: str)
  📍 Location Path: root
      └── • dueDate                      (Types: str)
      └── • dateComplete                 (Types: str)
      └── • result                       (Types: str)
      └── • concernAreas                 (Types: str)
      └── • reminderDate                 (Types: str)

 Table: [ reminders ] change to reminder
  └── Foreign Key: user_id (FK -> users.id)
  └── Detected Columns:
      • daily                     (Types seen: dict) 
      • monthly                   (Types seen: dict)
      • take                      (Types seen: dict)
      • order                     (Types seen: dict)
      • collect                   (Types seen: dict)


    fields from dicts above
  📌 Field: daily  (dict (nested object))
      └── Content structure:
          • reminder                  -> bool
          • time                      -> str
          • method                    -> str
          • to                        -> str
  📌 Field: monthly  (dict (nested object))
      └── Content structure:
          • reminder                  -> bool
          • frequency                 -> str
          • start                     -> str
          • method                    -> str
          • to                        -> str
          • lastSent                  -> str
          • type                      -> str
  📌 Field: take  (dict (nested object))
      └── Content structure:
          • reminder                  -> bool
          • time                      -> str
          • method                    -> str
          • to                        -> str
  📌 Field: order  (dict (nested object))
      └── Content structure:
          • reminder                  -> bool
          • frequency                 -> str
          • start                     -> str
          • method                    -> str
          • to                        -> str
          • type                      -> str
          • lastSent                  -> str
  📌 Field: collect  (dict (nested object))
      └── Content structure:
          • reminder                  -> bool
          • frequency                 -> str
          • start                     -> str
          • method                    -> str
          • to                        -> str
          • type                      -> str
          • lastSent                  -> str

      need to change this table to add what was stored in a dictionary under the fields above
      

 Table: [ thoughts ] change to thought
  └── Foreign Key: user_id (FK -> users.id)
  └── Detected Columns:
      • #home/dealing-se/hot-flushes/thoughts/hfactivity (Types seen: list) check
      • #home/dealing-se/hot-flushes/thoughts/nsactivity (Types seen: list)
      • #home/dealing-se/mood/managing-mood (Types seen: list)
      • #home/dealing-se/sleep/cbt/changesleep (Types seen: list)

        📍 Location Path: {PATH}
      └── • [Type]                       (Types: list (array))
  📍 Location Path: {PATH}[]
      └── • negative                     (Types: str)
      └── • positive                     (Types: str)

 Table: [ favourites ] change to favourite
  └── Foreign Key: user_id (FK -> users.id)
  └── Detected Columns:
      • title                     (Types seen: str)
      • path                      (Types seen: str)