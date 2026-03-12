local M = {}

local ignored_filetypes = {
  ["neo-tree"] = true,
  Trouble = true,
  toggleterm = true,
}

function M.get()
  local buf = vim.api.nvim_get_current_buf()
  local filetype = vim.bo[buf].filetype
  if ignored_filetypes[filetype] or vim.bo[buf].buftype == "terminal" then
    return ""
  end

  local parts = {}
  local name = vim.fn.expand("%:t")
  if name == "" then
    name = "[No Name]"
  end
  table.insert(parts, name)

  local ok, navic = pcall(require, "nvim-navic")
  if ok and navic.is_available() then
    local location = navic.get_location()
    if location ~= "" then
      table.insert(parts, location)
    end
  end

  return table.concat(parts, "  >  ")
end

return M
