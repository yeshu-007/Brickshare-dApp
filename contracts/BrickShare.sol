// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract BrickShare is ERC20, Ownable, ReentrancyGuard {
    address public immutable adminA;
    address public immutable adminB;
    uint256 public immutable pricePerShare;
    uint256 public immutable totalSupplyCap;
    bool public saleActive = true;
    string public documentCid;
    mapping(address => bool) public isVerified;
    mapping(address => uint8) public approvalCount;
    mapping(address => mapping(address => bool)) public hasApproved;

    error NotAdmin(); error AlreadyApproved(); error AlreadyVerified(); error NotVerified(address account);
    error SaleNotActive(); error SupplyCapExceeded(); error IncorrectPayment(); error ZeroAddress();
    error DuplicateAdmin(); error EmptyDocument(); error NothingToWithdraw(); error WithdrawFailed();

    event InvestorApproved(address indexed investor, address indexed admin, uint8 approvals);
    event InvestorVerified(address indexed investor);
    event TokensPurchased(address indexed buyer, uint256 amount, uint256 ethPaid);
    event DocumentUpdated(string cid);
    event SaleStatusChanged(bool active);
    event Withdrawn(address indexed to, uint256 amount);

    constructor(string memory name_, string memory symbol_, address adminA_, address adminB_, uint256 pricePerShare_, uint256 supplyCap_)
        ERC20(name_, symbol_) Ownable(msg.sender) {
        if (adminA_ == address(0) || adminB_ == address(0)) revert ZeroAddress();
        if (adminA_ == adminB_) revert DuplicateAdmin();
        adminA = adminA_; adminB = adminB_; pricePerShare = pricePerShare_; totalSupplyCap = supplyCap_;
    }

    function decimals() public pure override returns (uint8) { return 0; }
    function isAdmin(address account) public view returns (bool) { return account == adminA || account == adminB; }
    function sharesRemaining() public view returns (uint256) { return totalSupplyCap - totalSupply(); }

    function approveInvestor(address investor) external {
        if (!isAdmin(msg.sender)) revert NotAdmin();
        if (isVerified[investor]) revert AlreadyVerified();
        if (hasApproved[investor][msg.sender]) revert AlreadyApproved();
        hasApproved[investor][msg.sender] = true;
        approvalCount[investor] += 1;
        emit InvestorApproved(investor, msg.sender, approvalCount[investor]);
        if (approvalCount[investor] == 2) { isVerified[investor] = true; emit InvestorVerified(investor); }
    }

    function buy(uint256 amount) external payable nonReentrant {
        if (!saleActive) revert SaleNotActive();
        if (!isVerified[msg.sender]) revert NotVerified(msg.sender);
        if (amount == 0 || totalSupply() + amount > totalSupplyCap) revert SupplyCapExceeded();
        if (msg.value != amount * pricePerShare) revert IncorrectPayment();
        _mint(msg.sender, amount);
        emit TokensPurchased(msg.sender, amount, msg.value);
    }

    function setDocument(string calldata cid) external onlyOwner {
        if (bytes(cid).length == 0) revert EmptyDocument();
        documentCid = cid; emit DocumentUpdated(cid);
    }
    function setSaleActive(bool active) external onlyOwner { saleActive = active; emit SaleStatusChanged(active); }
    function withdraw() external onlyOwner nonReentrant {
        uint256 amount = address(this).balance; if (amount == 0) revert NothingToWithdraw();
        (bool ok,) = payable(owner()).call{value: amount}(""); if (!ok) revert WithdrawFailed(); emit Withdrawn(owner(), amount);
    }
    function _update(address from, address to, uint256 value) internal override {
        if (to != address(0) && !isVerified[to]) revert NotVerified(to);
        super._update(from, to, value);
    }
}
