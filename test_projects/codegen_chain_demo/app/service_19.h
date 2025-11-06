#pragma once
#include <functional>
#include <vector>

class Service19 {
public:
    Service19();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
