
`[POST] /api/projects/{project_name}/lists`
create a new entity list

`[POST] /api/projects/{project_name}/lists/{list_id}/items`
add a new item to an existing entity list

`[PATCH] /api/projects/{project_name}/lists/{list_id}`
update an existing entity list

`[PATCH] /api/projects/{project_name}/lists/{list_id}/items/{item_id}`
update an existing item in an entity list (including changing its position)

`[POST] /api/projects/{project_name}/lists/{list_id}/order`
reorder items in an entity list

`[POST] /api/projects/{project_name}/lists/{list_id}/materialize`
materialize an entity list items using its template

`[DELETE] /api/projects/{project_name}/lists/{list_id}`
delete an existing entity list (including all its items)

`[DELETE] /api/projects/{project_name}/lists/{list_id}/items/{item_id}`
delete an existing item from an entity list
