#pragma once
#include <functional>
#include <vector>

class Service9 {
public:
    Service9();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
