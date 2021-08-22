function updateTable(tableName) {
    return (table, row) => {
        var newRows = [];
        let rows = table.tBodies[0].rows
        for (let i=0; i<rows.length; i++) {
            newRows.push(rows[i].id.split("_")[1]);
            rows[i].children[1].firstElementChild.textContent = i+1
        }
        console.log(newRows);
        $(`#${tableName}`).val(newRows)
    }
}

$(document).ready(function() {
    // https://github.com/isocra/TableDnD
    $("#statuses").tableDnD({
        onDrop: updateTable("statusOrder")
    });
    $("#tables").tableDnD({
        onDrop: updateTable("tableOrder")
    });

    let statusOrder = []
    let statusRows = $("#statuses > tbody > tr")
    for (let i=0; i<statusRows.length; i++) {
        statusOrder.push(statusRows[i].id.split("_")[1]);
    }
    $("#statusOrder").val(statusOrder);

    let tableOrder = []
    let tableRows = $("#tables > tbody > tr")
    for (let i=0; i<tableRows.length; i++) {
        tableOrder.push(tableRows[i].id.split("_")[1]);
    }
    $("#tableOrder").val(tableOrder);
});

$("#newstatus").click(() => {
    $("#statuses tr:last").after(
        `<tr id="status_${statusNumber}" style="cursor: move;">
            <td>⇅</td>
            <td>
            <p>${statusNumber}<p>
            <input
                class="form-control"
                type="hidden"
                id="status_${statusNumber}_position"
                name="status_${statusNumber}_position"
                value="${statusNumber}"
            />
            </td>
            <td>
            <input
                class="form-control"
                type="text"
                id="status_${statusNumber}_name"
                name="status_${statusNumber}_name"
                placeholder="Name"
            />
            </td>
            <td>
            <input
                class="form-control"
                type="checkbox"
                name="status_${statusNumber}_orderByPosition"
                id="status_${statusNumber}_orderByPosition"
            />
            </td>
        </tr>`
    );
    $("#statuses").tableDnDUpdate();
    let statusOrder = $("#statusOrder").val()
    newOrder = []
    statusOrder.split(",").forEach(val => {
        newOrder.push(parseInt(val));
    });
    newOrder.push(statusNumber);
    $("#statusOrder").val(newOrder);
    statusNumber++;
});


$("#newtable").click(() => {
    $("#tables tr:last").after(
        `<tr id="table_${tableNumber}" style="cursor: move;">
            <td>⇅</td>
            <td>
            <p>${tableNumber}</p>
            <input
                class="form-control"
                type="hidden"
                id="table_${tableNumber}_position"
                name="table_${tableNumber}_position"
                value="${tableNumber}"
            />
            </td>
            <td>
            <input
                class="form-control"
                type="text"
                id="table_${tableNumber}_name"
                name="table_${tableNumber}_name"
                placeholder="Name"
            />
            </td>
            <td>
            <input
                class="form-control"
                type="checkbox"
                name="table_${tableNumber}_active"
                id="table_${tableNumber}_active"
                checked
            />
            </td>
      </tr>`
    );
    $("#tables").tableDnDUpdate();
    let tableOrder = $("#tableOrder").val()
    newOrder = []
    tableOrder.split(",").forEach(val => {
        newOrder.push(parseInt(val));
    });
    newOrder.push(tableNumber);
    console.log(newOrder);
    $("#tableOrder").val(newOrder);
    tableNumber++;
});